from __future__ import annotations

import asyncio
import hashlib
import importlib
import inspect
import json
import os
import re
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from fastmcp.tools.base import ToolResult
from mcp.types import CallToolResult, TextContent
from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import BrowserContext as PlaywrightBrowserContext

from camoufox_playwright_mcp.mcp.config import ServerConfig

from .context import Context
from .response import Response
from .session_log import SessionLog
from .tool import Tool, ToolValidationError

if TYPE_CHECKING:
    from .extension_relay import CDPRelayServer


class BrowserBackend:
    """Thin browser backend dispatcher.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/browserBackend.ts
    """

    def __init__(
        self,
        config: ServerConfig,
        tools: list[Tool],
        *,
        shared_browser_owner: BrowserBackend | None = None,
        close_shared_browser: bool = True,
        close_browser_context: bool = True,
        browser_context: PlaywrightBrowserContext | None = None,
    ) -> None:
        self._config = config
        self._tools = {tool.name: tool for tool in tools}
        self._shared_browser_owner = shared_browser_owner
        self._close_shared_browser = close_shared_browser
        self._close_browser_context = close_browser_context
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._playwright_context: PlaywrightBrowserContext | None = browser_context
        self._supplied_browser_context = browser_context is not None
        self._extension_relay: CDPRelayServer | None = None
        self._context: Context | None = None
        self._session_log: SessionLog | None = None
        self._disconnected = False
        self._closed = False
        self._disconnect_listeners_registered = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def has_page(self) -> bool:
        return self._context is not None and self._context.has_tab()

    async def call_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        roots: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            return _format_error(f'Tool "{name}" not found', json_mode=bool(meta and meta.get("json")))

        client_cwd = _client_cwd(meta=meta, roots=roots)
        result: str | ToolResult | CallToolResult

        try:
            context = await self._ensure_context(cwd=client_cwd, roots=roots)
            try:
                parsed_args = tool.validate(args)
            except ToolValidationError as exc:
                return _format_error(
                    f'Invalid arguments for tool "{name}":\n{exc}',
                    json_mode=bool(meta and meta.get("json")),
                )
            response = Response(
                context,
                tool_name=name,
                tool_args=parsed_args,
                relative_to=client_cwd,
                raw=bool(meta and meta.get("raw")),
                json_mode=bool(meta and meta.get("json")),
            )
            context.set_running_tool(name)
            tab = context.current_tab()
            if tab is not None:
                await tab.prune_stale_dialogs()
            if _blocks_on_modal_state(context, tool):
                if tool.clears_modal_state:
                    response.add_error(
                        f'Error: The tool "{name}" can only be used when there is related modal state present.'
                    )
                else:
                    response.add_error(
                        f'Error: Tool "{name}" does not handle the modal state. '
                        f'Use {_modal_clearing_hint(context)} to clear it first.'
                    )
                result = await response.serialize()
                if self._disconnected:
                    result = _attach_close_marker(result)
                    await self.close()
                return result
            await tool.handler(context, parsed_args, response)
            _drain_unhandled_errors(context, response)
            result = await response.serialize()
            if self._session_log is not None:
                await self._session_log.log_response(name, parsed_args, result)
        except ValueError as exc:
            messages = [str(exc)]
            if self._context is not None:
                messages.extend(getattr(self._context, "drain_unhandled_errors", list)())
            result = _format_error("\n\n".join(messages), json_mode=bool(meta and meta.get("json")))
            if self._disconnected:
                result = _attach_close_marker(result)
                await self.close()
            return result
        except Exception as exc:
            messages = [_format_exception(exc)]
            if self._context is not None:
                messages.extend(getattr(self._context, "drain_unhandled_errors", list)())
            result = _format_error("\n\n".join(messages), json_mode=bool(meta and meta.get("json")))
            if self._disconnected:
                result = _attach_close_marker(result)
                await self.close()
            return result
        finally:
            if self._context is not None:
                self._context.set_running_tool(None)

        if response.is_close or self._disconnected:
            result = _attach_close_marker(result)
            await self.close()
        return result

    async def close(self) -> None:
        browser_context = self._context.browser_context() if self._context is not None else None
        try:
            if self._context is not None:
                with suppress(Exception):
                    await self._context.dispose()
            if browser_context is not None and self._should_close_browser_context():
                with suppress(Exception):
                    await browser_context.close()
            if self._browser is not None and self._shared_browser_owner is None:
                with suppress(Exception):
                    await self._browser.close()
            if self._extension_relay is not None:
                with suppress(Exception):
                    await self._extension_relay.stop()
            if self._playwright is not None and self._shared_browser_owner is None:
                with suppress(Exception):
                    await self._playwright.stop()
        finally:
            self._playwright = None
            if self._close_shared_browser and self._shared_browser_owner is not None:
                with suppress(Exception):
                    await self._shared_browser_owner.close()
            self._browser = None
            self._playwright_context = None
            self._extension_relay = None
            self._context = None
            self._session_log = None
            self._disconnected = False
            self._closed = True
            self._disconnect_listeners_registered = False

    def _should_close_browser_context(self) -> bool:
        if not self._close_browser_context:
            return False
        if self._playwright_context is not None:
            return False
        return True

    async def render_page_markdown(self) -> list[str]:
        tab = await self._ensure_tab()
        return await tab.render_page_markdown()

    async def capture_snapshot(
        self,
        *,
        target: str | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str:
        tab = await self._ensure_tab()
        return await tab.capture_snapshot(target=target, depth=depth, boxes=boxes)

    async def _ensure_tab(self):
        cwd = self._context.cwd if self._context is not None else Path.cwd()
        context = await self._ensure_context(cwd=cwd, roots=None)
        return await context.ensure_tab()

    async def _ensure_context(self, *, cwd: Path, roots: list[str] | None) -> Context:
        if self._context is not None:
            self._closed = False
            self._context.configure_client(
                roots=[Path(root) for root in roots] if roots is not None else None,
                cwd=cwd,
            )
            return self._context
        if self._shared_browser_owner is not None:
            self._browser = await self._shared_browser_owner._ensure_browser(cwd)
        if self._shared_browser_owner is None and self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._config.test_id_attribute)
        if self._browser is None and self._playwright_context is None:
            self._browser = await self._launch_browser(cwd)
        if self._playwright_context is not None:
            if self._supplied_browser_context and self._config.browser_isolated:
                raise ValueError("Creating a new context is not supported for supplied browser contexts.")
            browser_context = self._playwright_context
        else:
            assert self._browser is not None
            if not self._config.browser_isolated and self._browser.contexts:
                browser_context = self._browser.contexts[0]
            else:
                if self._config.browser_provider == "camoufox":
                    camoufox_async_api = importlib.import_module("camoufox.async_api")
                    async_new_context = camoufox_async_api.AsyncNewContext
                    valid_context_keys = {"preset", "os", "ff_version", "webrtc_ip", "proxy", "geolocation", "locale", "timezone_id"}
                    filtered_camoufox_options = {k: v for k, v in self._config.camoufox_options.items() if k in valid_context_keys}
                    browser_context = await async_new_context(
                        self._browser,
                        **filtered_camoufox_options,
                        **self._config.browser_context_options,
                    )
                else:
                    browser_context = await self._browser.new_context(**self._config.browser_context_options)
        self._register_disconnect_listeners(browser_context)
        if self._config.action_timeout is not None:
            browser_context.set_default_timeout(self._config.action_timeout)
        if self._config.navigation_timeout is not None:
            browser_context.set_default_navigation_timeout(self._config.navigation_timeout)
        self._context = Context(browser_context, self._config, cwd=cwd)
        self._context.configure_client(
            roots=[Path(root) for root in roots] if roots is not None else None,
            cwd=cwd,
        )
        await self._context.initialize()
        self._closed = False
        if self._config.save_session:
            self._session_log = await SessionLog.create(self._context)
            self._context.session_log = self._session_log
        return self._context

    async def _ensure_browser(self, cwd: Path) -> Browser:
        if self._browser is not None:
            return self._browser
        if self._playwright is None:
            self._playwright = await async_playwright().start()
            self._playwright.selectors.set_test_id_attribute(self._config.test_id_attribute)
        if self._browser is None and self._playwright_context is None:
            self._browser = await self._launch_browser(cwd)
        if self._browser is None and self._playwright_context is not None:
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Persistent browser context did not expose a browser instance.")
            self._browser = browser
        assert self._browser is not None
        return self._browser

    async def _launch_browser(self, cwd: Path | None = None) -> Browser:
        cwd = cwd or Path.cwd()
        assert self._playwright is not None
        if self._config.cdp_endpoint:
            connect_kwargs: dict[str, Any] = {
                "headers": self._config.cdp_headers,
                "timeout": self._config.cdp_timeout,
            }
            if "artifacts_dir" in inspect.signature(
                self._playwright.chromium.connect_over_cdp
            ).parameters:
                connect_kwargs["artifacts_dir"] = self._traces_dir(cwd)
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._config.cdp_endpoint,
                **connect_kwargs,
            )
            return self._browser
        if self._config.remote_endpoint:
            remote = self._config.remote_endpoint
            if isinstance(remote, str):
                connect_endpoint = remote
                remote_connect_kwargs: dict[str, Any] = {}
                if self._config.remote_headers:
                    remote_connect_kwargs["headers"] = self._config.remote_headers
            else:
                remote_connect_kwargs = dict(remote)
                connect_endpoint = remote_connect_kwargs.pop("endpoint", "")
                if self._config.remote_headers:
                    headers = remote_connect_kwargs.pop("headers", None)
                    merged = dict(self._config.remote_headers)
                    if isinstance(headers, dict):
                        merged.update(headers)
                    remote_connect_kwargs["headers"] = merged
            descriptor = await _server_registry_find(connect_endpoint)
            if descriptor is not None:
                browser = descriptor.get("browser") or {}
                browser_name = str(browser.get("browserName") or self._config.browser_name)
                endpoint = str(descriptor.get("endpoint") or descriptor.get("pipeName") or "")
                browser_type = getattr(self._playwright, browser_name)
                self._browser = await browser_type.connect(endpoint)
            else:
                browser_type = getattr(self._playwright, self._config.browser_name)
                self._browser = await browser_type.connect(connect_endpoint, **remote_connect_kwargs)
            # A browser started via `launchServer` has no contexts; create one.
            if not self._browser.contexts:
                await self._browser.new_context(**self._config.browser_context_options)
            return self._browser
        if self._config.extension:
            if self._config.browser_name != "chromium":
                raise ValueError(
                    f'Extension mode (--extension) is only supported with Chromium-based browsers, '
                    f'got "{self._config.browser_name}".'
                )
            try:
                from .extension_relay import CDPRelayServer
            except ModuleNotFoundError as exc:
                if exc.name and exc.name.startswith("websockets"):
                    raise ValueError(
                        '--extension requires the optional "extension" dependency group. '
                        'Install camoufox-playwright-mcp[extension].'
                    ) from exc
                raise
            self._extension_relay = CDPRelayServer(
                self._playwright,
                browser_channel=self._config.browser_channel or self._config.browser,
                executable_path=self._config.browser_launch_options.get("executable_path"),
                user_data_dir=self._config.browser_user_data_dir,
            )
            await self._extension_relay.start()
            await self._extension_relay.establish_extension_connection("camoufox-playwright-mcp")
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._extension_relay.cdp_endpoint(),
                timeout=0,
            )
            return self._browser

        if self._config.browser_provider == "camoufox":
            return await self._launch_camoufox(cwd)

        launch_options = dict(self._config.browser_launch_options)
        headless = bool(launch_options.get("headless", self._config.headless))
        if not headless and os.name == "posix" and not os.environ.get("DISPLAY"):
            headless = True
        launch_options["headless"] = headless
        launch_options.setdefault("traces_dir", self._traces_dir(cwd))
        launch_options["handle_sigint"] = False
        launch_options["handle_sigterm"] = False

        browser_type = getattr(self._playwright, self._config.browser_name)
        if self._config.browser_user_data_dir is not None and self._config.browser_isolated:
            raise ValueError("Browser userDataDir is not supported in isolated mode.")
        if not self._config.browser_isolated:
            user_data_dir = self._config.browser_user_data_dir or await self._default_user_data_dir(cwd)
            _clear_stale_profile_locks(user_data_dir)
            if await _is_profile_locked_5_times(user_data_dir):
                owner = _profile_lock_owner_description(user_data_dir)
                raise ValueError(
                    f"Browser is already in use for {user_data_dir}{owner}. "
                    "Stop the other run (or wait for it to finish) before "
                    "starting another browser on the same profile, or use "
                    "--isolated to run multiple instances of the same browser"
                )
            launch_options["ignore_default_args"] = _persistent_ignore_default_args(
                launch_options.get("ignore_default_args")
            )
            try:
                self._playwright_context = await browser_type.launch_persistent_context(
                    user_data_dir,
                    **launch_options,
                    **self._config.browser_context_options,
                )
            except Exception as exc:
                if await _is_profile_locked_5_times(user_data_dir):
                    owner = _profile_lock_owner_description(user_data_dir)
                    raise RuntimeError(
                        f"Browser profile {user_data_dir} is in use by another "
                        f"running browser{owner}. Stop the other run (or wait for "
                        "it to finish) before starting another browser on the same "
                        "profile, or use --isolated to run multiple instances of "
                        "the same browser"
                    ) from exc
                raise _map_browser_launch_error(exc, self._config, user_data_dir, launch_options) from exc
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Persistent browser context did not expose a browser instance.")
            return browser
        try:
            return await browser_type.launch(**launch_options)
        except Exception as exc:
            raise _map_browser_launch_error(exc, self._config, None, launch_options) from exc

    async def _launch_camoufox(self, cwd: Path) -> Browser:
        try:
            camoufox_async_api = importlib.import_module("camoufox.async_api")
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.startswith("camoufox"):
                raise ValueError(
                    "Camoufox is required. Run "
                    "`camoufox-playwright-mcp install-browser` or `pip install 'camoufox[geoip]'`."
                ) from exc
            raise
        async_new_browser: Any = camoufox_async_api.AsyncNewBrowser

        launch_options = dict(self._config.browser_launch_options)
        camoufox_options = dict(self._config.camoufox_options)
        for unsupported in ("channel", "chromium_sandbox", "executable_path"):
            launch_options.pop(unsupported, None)
        try:
            import camoufox.pkgman
            camoufox.pkgman.launch_path()
        except Exception:
            try:
                import camoufox.pkgman
                camoufox.pkgman.CamoufoxFetcher().install()
            except Exception:
                pass

        headless = launch_options.pop("headless", self._config.headless)
        camoufox_options.setdefault("headless", headless)
        launch_options.setdefault("traces_dir", self._traces_dir(cwd))
        launch_options["handle_sigint"] = False
        launch_options["handle_sigterm"] = False

        if self._config.browser_user_data_dir is not None and self._config.browser_isolated:
            raise ValueError("Browser userDataDir is not supported in isolated mode.")
        if not self._config.browser_isolated:
            user_data_dir = self._config.browser_user_data_dir or await self._default_user_data_dir(cwd)
            _clear_stale_profile_locks(user_data_dir)
            if await _is_profile_locked_5_times(user_data_dir):
                owner = _profile_lock_owner_description(user_data_dir)
                raise ValueError(
                    f"Browser is already in use for {user_data_dir}{owner}. "
                    "Stop the other run (or wait for it to finish) before "
                    "starting another browser on the same profile, or use "
                    "--isolated to run multiple instances of the same browser"
                )
            try:
                combined_opts = {
                    **launch_options,
                    **self._config.browser_context_options,
                    **camoufox_options
                }
                self._playwright_context = await async_new_browser(
                    self._playwright,
                    persistent_context=True,
                    user_data_dir=str(user_data_dir),
                    **combined_opts,
                )
            except Exception as exc:
                if await _is_profile_locked_5_times(user_data_dir):
                    owner = _profile_lock_owner_description(user_data_dir)
                    raise RuntimeError(
                        f"Browser profile {user_data_dir} is in use by another "
                        f"running browser{owner}. Stop the other run (or wait for "
                        "it to finish) before starting another browser on the same "
                        "profile, or use --isolated to run multiple instances of "
                        "the same browser"
                    ) from exc
                raise _map_browser_launch_error(exc, self._config, user_data_dir, launch_options) from exc
            browser = self._playwright_context.browser
            if browser is None:
                raise ValueError("Camoufox persistent context did not expose a browser instance.")
            return browser
        try:
            return await async_new_browser(
                self._playwright,
                persistent_context=False,
                **launch_options,
                **camoufox_options,
            )
        except Exception as exc:
            raise _map_browser_launch_error(exc, self._config, None, launch_options) from exc

    def _traces_dir(self, cwd: Path | None = None) -> Path:
        cwd = cwd or Path.cwd()
        return _output_dir(self._config, cwd) / "traces"

    async def _default_user_data_dir(self, cwd: Path | None = None) -> Path:
        cwd = cwd or Path.cwd()
        cache_root = (
            Path(os.environ["PWMCP_PROFILES_DIR_FOR_TEST"])
            if os.environ.get("PWMCP_PROFILES_DIR_FOR_TEST")
            else _cache_root() / "ms-playwright-mcp"
        )
        browser_token = (
            "camoufox"
            if self._config.browser_provider == "camoufox"
            else (self._config.browser_channel or self._config.browser_name)
        )
        cwd_hash = hashlib.sha256(str(cwd).encode()).hexdigest()[:7]
        user_data_dir = cache_root / f"mcp-{browser_token}-{cwd_hash}"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        return user_data_dir

    def _register_disconnect_listeners(self, browser_context: PlaywrightBrowserContext) -> None:
        if self._disconnect_listeners_registered:
            return

        def mark_disconnected(*_args: Any) -> None:
            self._disconnected = True

        browser_context.on("close", mark_disconnected)
        browser = browser_context.browser
        if browser is not None:
            browser.on("disconnected", mark_disconnected)
        self._disconnect_listeners_registered = True


def _blocks_on_modal_state(context: Context, tool: Tool) -> bool:
    if not tool.blocks_on_modal_state and tool.clears_modal_state is None:
        return False
    tab = context.current_tab()
    if tab is None:
        return False
    modal_states = tab.modal_states()
    if not modal_states:
        return tool.clears_modal_state is not None
    if tool.clears_modal_state is not None:
        return not any(state.get("type") == tool.clears_modal_state for state in modal_states)
    return True


def _modal_clearing_hint(context: Context) -> str:
    tab = context.current_tab()
    if tab is None:
        return "browser_handle_dialog"
    tools = sorted(
        {
            str(state.get("clearedBy", {}).get("tool"))
            for state in tab.modal_states()
            if state.get("clearedBy")
        }
    )
    return ", ".join(tools) if tools else "browser_handle_dialog"


def _drain_unhandled_errors(context: Context, response: Response) -> None:
    errors: list[str] = getattr(context, "drain_unhandled_errors", list)()
    for error in errors:
        response.add_error(error)


def _format_exception(exc: Exception) -> str:
    # Sanitize: do not leak absolute paths / full traceback (seen on NS_ERROR_UNKNOWN_HOST).
    # Vallidation errors from FastMCP/pydantic arrive as "validation errors for call[_tool_handler]"
    # which we reformat to match official: 'Invalid arguments for tool "X":'
    msg = str(exc).strip()
    low = msg.lower()
    if "validation errors for call" in low or "missing required keyword" in low or "unexpected keyword argument" in low:
        # Extract a concise summary; keep original msg but without traceback header and file paths
        # Try to pull field names
        # Example: "2 validation errors for call[_tool_handler]\ntarget\n  Missing required..."
        # We return just the validation part without the "for call..." prefix
        # and strip the file-path traceback if present
        # Remove the "validation errors for call..." line
        # Remove first line like "2 validation errors for call[_tool_handler]"
        lines_tmp = msg.splitlines()
        if lines_tmp and "validation errors for call" in lines_tmp[0].lower():
            msg = "\n".join(lines_tmp[1:])
        msg = re.sub(r"^\d+ validation errors.*", "", msg, flags=re.IGNORECASE|re.MULTILINE)
        # Strip "For further information visit https://errors.pydantic.dev/..." lines
        msg = re.sub(r"For further information visit.*", "", msg)
        msg = "\n".join(line.strip() for line in msg.splitlines() if line.strip())
        # If we can infer tool, caller will wrap with "Invalid arguments for tool"
        # Return raw validation lines; the caller in server.py will wrap
        return msg or str(exc).strip()
    # For Playwright errors, str(exc) already contains call log; trim any absolute path leakage
    # Remove lines that look like 'File "/home/..."'
    lines = []
    for line in msg.splitlines():
        if 'File "/' in line and "camoufox_playwright_mcp" in line:
            continue
        if line.strip().startswith('File "') and ".venv" in line:
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    return cleaned or str(exc).strip()


def _map_browser_launch_error(
    exc: Exception,
    config: ServerConfig,
    user_data_dir: Path | None,
    launch_options: dict[str, Any],
) -> Exception:
    message = str(exc)
    browser_name = launch_options.get("channel") or config.browser_channel or config.browser_name
    if "Camoufox is not installed" in message or "camoufox fetch" in message:
        return RuntimeError(
            "Camoufox browser binary is not installed. "
            "Run `camoufox-playwright-mcp install-browser` (or `uvx camoufox-playwright-mcp install-browser`) to download it."
        )
    if "Executable doesn't exist" in message:
        target = "ffmpeg" if "ffmpeg" in message else browser_name
        label = "FFmpeg" if target == "ffmpeg" else f'Browser "{target}"'
        return RuntimeError(f"{label} is not installed. Run `camoufox-playwright-mcp install-browser {target}` to install")
    if "cannot open shared object file: No such file or directory" in message:
        return RuntimeError(
            f"Missing system dependencies required to run browser {browser_name}. "
            f"Install them with: sudo playwright install-deps {browser_name}"
        )
    if user_data_dir is not None and ("ProcessSingleton" in message or "exitCode=21" in message):
        return RuntimeError(
            f"Browser is already in use for {user_data_dir}, use --isolated to run multiple instances of the same browser"
        )
    return exc


def _output_dir(config: ServerConfig, cwd: Path) -> Path:
    if config.output_dir is not None:
        return config.output_dir.resolve()
    base_name = ".playwright-mcp"
    if _is_system_directory(cwd) or not os.access(cwd, os.W_OK):
        return Path(tempfile.gettempdir()) / base_name
    return cwd / base_name


def _client_cwd(*, meta: dict[str, Any] | None, roots: list[str] | None) -> Path:
    if meta and meta.get("cwd"):
        return Path(str(meta["cwd"]))
    if roots:
        return Path(roots[0])
    return Path.cwd()


def _format_error(message: str, *, json_mode: bool) -> ToolResult:
    if json_mode:
        return ToolResult(content=json.dumps({"isError": True, "error": message}, indent=2), is_error=True)
    return ToolResult(content=f"### Error\n{message}", is_error=True)


def _attach_close_marker(result: str | ToolResult | CallToolResult) -> CallToolResult:
    if isinstance(result, CallToolResult):
        data = result.model_dump(by_alias=True)
        data["_meta"] = {**(data.get("_meta") or {}), "isClose": True}
        return CallToolResult(**data)
    if isinstance(result, ToolResult):
        converted = result.to_mcp_result()
        if isinstance(converted, CallToolResult):
            data = converted.model_dump(by_alias=True)
            data["_meta"] = {**(data.get("_meta") or {}), "isClose": True}
            return CallToolResult(**data)
        if isinstance(converted, tuple):
            content, structured_content = converted
            return CallToolResult(
                content=content,
                structuredContent=structured_content,
                _meta={"isClose": True},
            )
        return CallToolResult(content=converted, _meta={"isClose": True})
    return CallToolResult(content=[TextContent(type="text", text=result)], _meta={"isClose": True})


async def _server_registry_find(name: str) -> dict[str, Any] | None:
    registry_dir = _server_registry_dir()
    if not registry_dir.exists():
        return None
    for file_path in registry_dir.iterdir():
        if not file_path.is_file():
            continue
        try:
            descriptor = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if descriptor.get("title") != name:
            continue
        if await _can_connect_to_descriptor(descriptor):
            return descriptor
        with suppress(OSError):
            file_path.unlink()
    return None


def _server_registry_dir() -> Path:
    if os.environ.get("PWTEST_SERVER_REGISTRY"):
        return Path(os.environ["PWTEST_SERVER_REGISTRY"])
    return _cache_root() / "ms-playwright" / "b"


async def _can_connect_to_descriptor(descriptor: dict[str, Any]) -> bool:
    endpoint = descriptor.get("endpoint") or descriptor.get("pipeName")
    if not isinstance(endpoint, str) or not endpoint:
        return False
    try:
        if endpoint.startswith(("ws://", "wss://")):
            parsed = urlparse(endpoint)
            if parsed.hostname is None:
                return False
            port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            _, writer = await asyncio.wait_for(asyncio.open_connection(parsed.hostname, port), timeout=1)
        elif os.name != "nt":
            _, writer = await asyncio.wait_for(asyncio.open_unix_connection(endpoint), timeout=1)
        else:
            return False
        writer.close()
        with suppress(Exception):
            await writer.wait_closed()
        return True
    except Exception:
        return False


def _cache_root() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")


def _is_system_directory(path: Path) -> bool:
    resolved = path.resolve()
    return resolved in {Path("/"), Path("/tmp"), Path("/var"), Path("/usr"), Path("/bin"), Path("/etc")}


def _persistent_ignore_default_args(value: Any) -> bool | list[str]:
    if value is True:
        return True
    args: list[str] = [str(item) for item in value] if isinstance(value, list) else []
    return ["--disable-extensions", *args]


async def _is_profile_locked_5_times(user_data_dir: Path) -> bool:
    for _ in range(5):
        if not _is_profile_locked(user_data_dir):
            return False
        await asyncio.sleep(1)
    return True


def _is_profile_locked(user_data_dir: Path) -> bool:
    """Whether another live process holds the browser profile.

    Two lock mechanisms exist: the classic ``SingletonLock`` symlink (owns a
    pid in its target) and the modern Firefox parent lock ``.parentlock`` (a
    plain empty file whose owning process cannot be read from the file). For
    ``.parentlock`` the profile is treated as locked only while a live process
    references this exact profile path; a stale lock left behind by a killed
    run is never treated as live.
    """
    lock_file = "lockfile" if os.name == "nt" else "SingletonLock"
    lock_path = user_data_dir / lock_file
    if os.name == "nt":
        if not lock_path.exists():
            return False
        try:
            with lock_path.open("r+b"):
                return False
        except OSError:
            return True

    try:
        target = os.readlink(lock_path)
        pid = int(target.rsplit("-", 1)[-1])
    except (OSError, ValueError):
        pass
    else:
        if _pid_alive(pid):
            return True

    if (user_data_dir / ".parentlock").exists():
        return _any_process_references_profile(user_data_dir)
    return False


def _clear_stale_profile_locks(user_data_dir: Path) -> None:
    """Remove profile lock artifacts whose owning process is gone.

    Firefox creates ``.parentlock`` at launch and removes it on clean exit; a
    killed or crashed run leaves it behind, and a later launch would refuse to
    use the profile. Only files with no live owner are removed, so an
    actively-used profile is never touched.
    """
    if os.name == "nt":
        return
    if _is_profile_locked(user_data_dir):
        return
    for name in ("SingletonLock", ".parentlock"):
        path = user_data_dir / name
        try:
            path.unlink()
        except OSError:
            continue


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _any_process_references_profile(user_data_dir: Path) -> bool:
    """Whether a live process has this profile path in its command line.

    The launching browser always receives ``-profile <path>``, so a live owner
    is visible in /proc even though ``.parentlock`` carries no pid. The
    scanning process itself is excluded.
    """
    if os.name == "nt" or not os.path.exists("/proc"):
        return False
    profile = str(user_data_dir.resolve())
    self_pid = os.getpid()
    for entry in os.scandir("/proc"):
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == self_pid:
            continue
        try:
            cmdline = Path(entry.path, "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if profile in cmdline:
            return True
    return False


def _profile_lock_owner_description(user_data_dir: Path) -> str:
    """Human-readable description of the live process holding the profile."""
    lock_file = "lockfile" if os.name == "nt" else "SingletonLock"
    lock_path = user_data_dir / lock_file
    try:
        target = os.readlink(lock_path)
        pid = int(target.rsplit("-", 1)[-1])
    except (OSError, ValueError):
        pid = None
    if not os.path.exists("/proc"):
        return f" (held by pid {pid})" if pid is not None else ""
    if pid is None:
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            try:
                cmdline = Path(entry.path, "cmdline").read_bytes().replace(b"\0", b" ").decode(
                    "utf-8", errors="replace"
                )
            except OSError:
                continue
            if str(user_data_dir.resolve()) in cmdline:
                return f" (held by pid {entry.name}: {cmdline[:120].strip()})"
        return ""
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        )
    except OSError:
        return f" (held by pid {pid})"
    return f" (held by pid {pid}: {command[:120].strip()})"
