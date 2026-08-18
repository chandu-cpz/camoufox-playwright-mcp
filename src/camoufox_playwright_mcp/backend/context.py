from __future__ import annotations

import asyncio
import inspect
import os
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import util as importlib_util
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from playwright.async_api import BrowserContext, Page

from camoufox_playwright_mcp.mcp.config import ServerConfig

from .codegen import python_literal

_BRING_TO_FRONT_TIMEOUT_SECONDS = 5.0

if TYPE_CHECKING:
    from .session_log import SessionLog
    from .tab import Tab


@dataclass(frozen=True, slots=True)
class FilenameTemplate:
    prefix: str
    ext: str
    suggested_filename: str | None = None
    date: datetime | None = None


@dataclass(frozen=True, slots=True)
class LookupSecret:
    value: str
    code: str


@dataclass(slots=True)
class RouteEntry:
    pattern: str
    status: int | None = None
    body: str | None = None
    content_type: str | None = None
    add_headers: dict[str, str] | None = None
    remove_headers: list[str] | None = None
    handler: Callable[[Any], Any] | None = None


@dataclass(frozen=True, slots=True)
class TraceLegend:
    traces_dir: Path
    name: str


@dataclass(slots=True)
class VideoRecording:
    params: dict[str, Any]
    file_names: list[Path]
    file_name: Path


class Context:
    """Browser-context runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/context.ts
    """

    def __init__(self, browser_context: BrowserContext, config: ServerConfig, *, cwd: Path | None = None) -> None:
        self.config = config
        self._browser_context = browser_context
        self._default_cwd = cwd or Path.cwd()
        self.cwd = self._default_cwd
        self.client_roots: list[Path] | None = None
        self._tabs: list[Tab] = []
        self._current_tab: Tab | None = None
        self._routes: list[RouteEntry] = []
        self._interception_routes: list[tuple[str, Callable[[Any], Any]]] = []
        self._listeners: list[tuple[Any, str, Callable[..., Any]]] = []
        self.session_log: SessionLog | None = None
        self.trace_legend: TraceLegend | None = None
        self._video_recording: VideoRecording | None = None
        self._pending_unhandled_errors: list[str] = []
        self._running_tool_name: str | None = None

    async def initialize(self) -> None:
        self._install_exception_handler()
        await self._setup_request_interception()
        for init_script in self.config.init_scripts:
            await self._browser_context.add_init_script(path=init_script)
        for page in self._browser_context.pages:
            self._on_page_created(page)

        def handle_page(page: Page) -> None:
            self._on_page_created(page)

        self._browser_context.on("page", handle_page)
        self._listeners.append((self._browser_context, "page", handle_page))

    def has_tab(self) -> bool:
        return self._current_tab is not None

    def tabs(self) -> list[Tab]:
        return self._tabs

    def browser_context(self) -> BrowserContext:
        return self._browser_context

    def configure_client(self, *, roots: list[Path] | None = None, cwd: Path | None = None) -> None:
        self.client_roots = roots
        if cwd is not None:
            self.cwd = cwd
        elif roots:
            self.cwd = roots[0]
        else:
            self.cwd = self._default_cwd

    def current_tab(self) -> Tab | None:
        return self._current_tab

    def current_tab_or_die(self) -> Tab:
        if self._current_tab is None:
            raise ValueError("No open pages available.")
        return self._current_tab

    async def dispose(self) -> None:
        self._restore_exception_handler()
        for target, event, handler in self._listeners:
            with suppress(Exception):
                target.remove_listener(event, handler)
        self._listeners.clear()
        for pattern, handler in self._interception_routes:
            with suppress(Exception):
                await self._browser_context.unroute(pattern, handler)
        self._interception_routes.clear()
        for tab in self._tabs:
            await tab.dispose()
        with suppress(Exception):
            await self.stop_video_recording()
        self._tabs.clear()
        self._current_tab = None

    async def ensure_tab(self) -> Tab:
        crashed = self._current_tab is not None and self._current_tab.crashed
        if crashed:
            crashed_tab = self._current_tab
            assert crashed_tab is not None
            with suppress(Exception):
                await crashed_tab.page.close()
            self._current_tab = None
        if self._current_tab is None:
            await self.new_tab()
        assert self._current_tab is not None
        if crashed:
            self._current_tab.log_error_message("Page crashed and was reset to about:blank.")
        return self._current_tab

    async def new_tab(self) -> Tab:
        page = await self._browser_context.new_page()
        tab = self._tab_for_page(page)
        if tab is None:
            tab = self._on_page_created(page)
        self._current_tab = tab
        return tab

    async def close_current_tab(self) -> None:
        tab = self._current_tab
        if tab is None:
            return
        await tab.close()

    async def close_tab(self, index: int | None = None) -> None:
        if index is None:
            await self.close_current_tab()
            return
        if index < 0 or index >= len(self._tabs):
            raise ValueError(f"Tab index {index} is out of range")
        await self._tabs[index].close()

    async def select_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tabs):
            raise ValueError(f"Tab index {index} is out of range")
        self._current_tab = self._tabs[index]
        try:
            async with asyncio.timeout(_BRING_TO_FRONT_TIMEOUT_SECONDS):
                await self._current_tab.page.bring_to_front()
        except TimeoutError:
            # Selecting the backend tab is authoritative for tool routing. A window
            # manager that cannot acknowledge foregrounding must not deadlock tools.
            pass

    async def set_offline(self, offline: bool) -> None:
        await self._browser_context.set_offline(offline)

    async def start_video_recording(self, file_name: Path, params: dict[str, Any]) -> None:
        if self._video_recording is not None:
            raise ValueError("Video recording has already been started.")
        self._video_recording = VideoRecording(params=params, file_names=[], file_name=file_name)
        for page in self._browser_context.pages:
            await self._start_page_video(page)

    async def stop_video_recording(self) -> list[Path]:
        recording = self._video_recording
        if recording is None:
            return []
        for page in self._browser_context.pages:
            with suppress(Exception):
                await page.screencast.stop()
        self._video_recording = None
        return list(recording.file_names)

    def routes(self) -> list[RouteEntry]:
        return list(self._routes)

    async def add_route(self, entry: RouteEntry) -> None:
        if entry.handler is None:
            raise ValueError("Route handler is required")
        await self._browser_context.route(entry.pattern, entry.handler)
        self._routes.append(entry)

    async def remove_route(self, pattern: str | None = None) -> int:
        if pattern is None:
            removed = len(self._routes)
            for entry in self._routes:
                await self._browser_context.unroute(entry.pattern, entry.handler)
            self._routes.clear()
            return removed
        removed_entries = [entry for entry in self._routes if entry.pattern == pattern]
        for entry in removed_entries:
            await self._browser_context.unroute(pattern, entry.handler)
        self._routes = [entry for entry in self._routes if entry.pattern != pattern]
        return len(removed_entries)

    async def check_url_and_navigate(self, url: str) -> str:
        resolved_url = self._resolve_url(url)
        self._check_url_allowed(resolved_url)
        tab = await self.ensure_tab()
        await tab.navigate(resolved_url)
        return resolved_url

    def _resolve_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme:
            return url
        if url.startswith("localhost"):
            return "http://" + url
        return "https://" + url

    def _check_url_allowed(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme == "file" and not self.config.allow_unrestricted_file_access:
            raise ValueError(f'Error: Access to "file:" protocol is blocked. Attempted URL: "{url}"')

    async def _setup_request_interception(self) -> None:
        if self.config.allowed_origins:
            await self._add_interception_route("**", _abort_route)
            for origin in self.config.allowed_origins:
                await self._add_interception_route(_origin_or_host_glob(origin), _continue_route)
        for origin in self.config.blocked_origins:
            await self._add_interception_route(_origin_or_host_glob(origin), _abort_route)

    async def _add_interception_route(self, pattern: str, handler: Callable[[Any], Any]) -> None:
        await self._browser_context.route(pattern, handler)
        self._interception_routes.append((pattern, handler))

    async def workspace_file(self, file_name: str, per_call_workspace_dir: Path | None = None) -> Path:
        workspace = per_call_workspace_dir or self.cwd
        resolved = (workspace / file_name).resolve()
        self._check_file(resolved, origin="llm")
        return resolved

    async def output_file(self, template: FilenameTemplate, *, origin: str) -> Path:
        date = template.date or datetime.now(UTC)
        safe_date = date.isoformat(timespec="milliseconds").replace("+00:00", "Z").replace(":", "-").replace(".", "-")
        base_name = template.suggested_filename or f"{template.prefix}-{safe_date}{'.' + template.ext if template.ext else ''}"
        resolved = (self.output_dir() / base_name).resolve()
        self._check_file(resolved, origin=origin)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def output_dir(self) -> Path:
        if self.config.output_dir is not None:
            return self.config.output_dir.resolve()
        base_name = ".playwright-mcp"
        if self._is_system_directory(self.cwd) or not os.access(self.cwd, os.W_OK):
            return Path(tempfile.gettempdir()) / base_name
        return self.cwd / base_name

    def redact_secrets(self, text: str) -> str:
        text = self._mask_text(text, (self.config.secrets or {}))
        text = self._mask_text(text, (self.config.redact_values or {}))
        return text

    @staticmethod
    def _mask_text(text: str, source: dict[str, str]) -> str:
        for name, value in source.items():
            if value:
                text = text.replace(value, f"<secret>{name}</secret>")
        return text

    def drain_unhandled_errors(self) -> list[str]:
        errors = list(self._pending_unhandled_errors)
        self._pending_unhandled_errors.clear()
        return errors

    def is_running_tool(self) -> bool:
        return self._running_tool_name is not None

    def set_running_tool(self, name: str | None) -> None:
        self._running_tool_name = name

    def track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        task.add_done_callback(self._capture_task_exception)
        return task

    def lookup_secret(self, secret_name: str) -> LookupSecret:
        # Intentionally reads ONLY config.secrets (credentials). config.redact_values
        # masks LLM-visible text but is deliberately NOT resolvable here, so PII
        # seeded via redact_values can never be fetched back by name.
        secret_value = (self.config.secrets or {}).get(secret_name)
        if secret_value is None:
            return LookupSecret(value=secret_name, code=python_literal(secret_name))
        return LookupSecret(value=secret_value, code=f"os.environ[{python_literal(secret_name)}]")

    def _check_file(self, resolved: Path, *, origin: str) -> None:
        if origin == "code" or self.config.allow_unrestricted_file_access:
            return
        output = self.output_dir().resolve()
        workspace = self.cwd.resolve()
        allowed_roots = [output, workspace]
        if not any(_is_relative_to(resolved, root.resolve()) for root in allowed_roots):
            roots_text = ", ".join(str(root) for root in allowed_roots)
            raise ValueError(f"File access denied: {resolved} is outside allowed roots. Allowed roots: {roots_text}")

    @staticmethod
    def _is_system_directory(path: Path) -> bool:
        resolved = path.resolve()
        return resolved in {Path("/"), Path("/tmp"), Path("/var"), Path("/usr"), Path("/bin"), Path("/etc")}

    def _on_page_closed(self, tab: Tab) -> None:
        if tab not in self._tabs:
            return
        index = self._tabs.index(tab)
        self._tabs.remove(tab)
        if self._current_tab is tab:
            self._current_tab = self._tabs[min(index, len(self._tabs) - 1)] if self._tabs else None

    def _on_page_crashed(self, tab: Tab) -> None:
        tab.crashed = True

    def _on_page_created(self, page: Any) -> Tab:
        from .tab import Tab

        existing = self._tab_for_page(page)
        if existing is not None:
            return existing
        tab = Tab(self, page)
        self._tabs.append(tab)
        if self._current_tab is None:
            self._current_tab = tab
        def close_listener(_event: Any = None) -> None:
            self._on_page_closed(tab)

        def crash_listener(_event: Any = None) -> None:
            self._on_page_crashed(tab)

        page.on("close", close_listener)
        page.on("crash", crash_listener)
        self._listeners.append((page, "close", close_listener))
        self._listeners.append((page, "crash", crash_listener))
        if self._video_recording is not None:
            self.track_task(asyncio.create_task(self._start_page_video(page)))
        return tab

    async def _start_page_video(self, page: Page) -> None:
        recording = self._video_recording
        if recording is None:
            return
        index = len(recording.file_names)
        file_name = recording.file_name
        if index:
            suffix = f"-{index}"
            file_name = file_name.with_name(f"{file_name.stem}{suffix}{file_name.suffix}")
        recording.file_names.append(file_name)
        params = {key: value for key, value in recording.params.items() if value is not None}
        await page.screencast.start(path=file_name, **params)

    def _tab_for_page(self, page: Any) -> Tab | None:
        return next((tab for tab in self._tabs if tab.page is page), None)

    def _install_exception_handler(self) -> None:
        loop = asyncio.get_running_loop()
        _ACTIVE_ERROR_CONTEXTS.add(self)
        _install_loop_exception_dispatcher(loop)

    def _restore_exception_handler(self) -> None:
        _ACTIVE_ERROR_CONTEXTS.discard(self)
        _restore_loop_exception_dispatcher_if_unused()

    def _capture_task_exception(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        try:
            exception = task.exception()
        except Exception as exc:
            exception = exc
        if exception is not None:
            self._pending_unhandled_errors.append(str(exception))

    async def run_init_pages(self, page: Page) -> None:
        for init_page in self.config.init_pages:
            await _run_init_page(init_page, page)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


async def _run_init_page(init_page: Path, page: Page) -> None:
    try:
        module_name = f"_playwright_mcp_init_page_{abs(hash(init_page))}"
        spec = importlib_util.spec_from_file_location(module_name, init_page)
        if spec is None or spec.loader is None:
            raise RuntimeError("Could not load module spec")
        module = importlib_util.module_from_spec(spec)
        spec.loader.exec_module(module)
        func = getattr(module, "init_page", None)
        if func is None:
            func = getattr(module, "default", None)
        if not callable(func):
            raise RuntimeError('Expected callable "init_page" or "default"')
        result = func(page)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:
        reason = str(exc)
        raise RuntimeError(f'Failed to load init page "{init_page}": {reason}') from exc


async def _abort_route(route: Any) -> None:
    await route.abort("blockedbyclient")


async def _continue_route(route: Any) -> None:
    await route.continue_()


def _origin_or_host_glob(origin_or_host: str) -> str:
    if origin_or_host.startswith(("http://", "https://")) and origin_or_host.endswith(":*"):
        return f"{origin_or_host}/**"
    parsed = urlparse(origin_or_host)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/**"
    return f"*://{origin_or_host}/**"


_ACTIVE_ERROR_CONTEXTS: set[Context] = set()
_DISPATCHER_LOOP: asyncio.AbstractEventLoop | None = None
_PREVIOUS_EXCEPTION_HANDLER: Callable[[asyncio.AbstractEventLoop, dict[str, Any]], object] | None = None
_DISPATCHER_HANDLER: Callable[[asyncio.AbstractEventLoop, dict[str, Any]], None] | None = None


def _install_loop_exception_dispatcher(loop: asyncio.AbstractEventLoop) -> None:
    global _DISPATCHER_LOOP, _PREVIOUS_EXCEPTION_HANDLER, _DISPATCHER_HANDLER
    if _DISPATCHER_LOOP is loop and _DISPATCHER_HANDLER is not None:
        return
    if _DISPATCHER_LOOP is not None and _DISPATCHER_LOOP is not loop:
        _restore_loop_exception_dispatcher_if_unused(force=True)
    _DISPATCHER_LOOP = loop
    _PREVIOUS_EXCEPTION_HANDLER = loop.get_exception_handler()

    def handler(current_loop: asyncio.AbstractEventLoop, event: dict[str, Any]) -> None:
        exception = event.get("exception")
        message = str(exception) if exception is not None else str(event.get("message", "Unhandled async exception"))
        for context in list(_ACTIVE_ERROR_CONTEXTS):
            context._pending_unhandled_errors.append(message)
        if _PREVIOUS_EXCEPTION_HANDLER is not None:
            _PREVIOUS_EXCEPTION_HANDLER(current_loop, event)

    _DISPATCHER_HANDLER = handler
    loop.set_exception_handler(handler)


def _restore_loop_exception_dispatcher_if_unused(*, force: bool = False) -> None:
    global _DISPATCHER_LOOP, _PREVIOUS_EXCEPTION_HANDLER, _DISPATCHER_HANDLER
    if not force and _ACTIVE_ERROR_CONTEXTS:
        return
    if _DISPATCHER_LOOP is not None and _DISPATCHER_LOOP.get_exception_handler() is _DISPATCHER_HANDLER:
        _DISPATCHER_LOOP.set_exception_handler(_PREVIOUS_EXCEPTION_HANDLER)
    _DISPATCHER_LOOP = None
    _PREVIOUS_EXCEPTION_HANDLER = None
    _DISPATCHER_HANDLER = None
