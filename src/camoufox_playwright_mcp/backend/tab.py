from __future__ import annotations

import asyncio
import inspect
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urlparse

from playwright.async_api import (
    ConsoleMessage,
    Dialog,
    Download,
    Error,
    FileChooser,
    Locator,
    Page,
    Request,
)
from playwright.async_api import (
    Response as PlaywrightResponse,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .locator_generator import as_python_locator
from .locator_parser import locator_or_selector_as_selector
from .log_file import LogFile
from .utils import sanitize_for_file_path

if TYPE_CHECKING:
    from .context import Context


logger = logging.getLogger(__name__)


Button = Literal["left", "middle", "right"]
Modifier = Literal["Alt", "Control", "ControlOrMeta", "Meta", "Shift"]
_REF_PATTERN = re.compile(r"^(?:f\d+)?e\d+$")
# A fresh Camoufox profile can need extra time to settle its network/geolocation
# state before the first document commit. Keep this bounded by the configured
# navigation timeout, but allow the default 60-second navigation budget before
# turning that startup work into a false navigation failure.
_COMMIT_ACK_TIMEOUT_MS = 120_000


@dataclass(slots=True)
class ResolvedTarget:
    locator: Locator
    code: str


@dataclass(slots=True)
class ConsoleEntry:
    type: str
    text: str
    location_url: str | None = None
    location_line: int | None = None
    navigation_index: int = 0

    def render(self) -> str:
        line = f"[{self.type.upper()}] {self.text}"
        if self.location_url:
            line += f" @ {self.location_url}"
            if self.location_line is not None:
                line += f":{self.location_line}"
        return line


@dataclass(slots=True)
class RequestEntry:
    request: Request
    response: PlaywrightResponse | None = None
    failure: str | None = None


@dataclass(slots=True)
class DocumentStatus:
    status: int
    status_text: str


@dataclass(slots=True)
class TabHeader:
    title: str
    url: str
    current: bool
    crashed: bool
    console: dict[str, int]
    main_document_status: DocumentStatus | None = None
    changed: bool = False


@dataclass(slots=True)
class TabSnapshot:
    aria_snapshot: str
    modal_states: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    console_link: str | None = None


class Tab:
    """Page-level runtime.

    Upstream responsibility:
    - packages/playwright-core/src/tools/backend/tab.ts
    """

    def __init__(self, context: Context, page: Page) -> None:
        self.context = context
        self.page = page
        self.crashed = False
        self._last_header = TabHeader(
            title="about:blank",
            url="about:blank",
            current=False,
            crashed=False,
            console={"total": 0, "errors": 0, "warnings": 0},
        )
        self._console_messages: list[ConsoleEntry] = []
        self._requests: list[RequestEntry] = []
        self._recent_event_entries: list[dict[str, Any]] = []
        self._modal_states: list[dict[str, Any]] = []
        self._modal_event = asyncio.Event()
        self._main_document_status: DocumentStatus | None = None
        self._navigation_index = 0
        self._console_log = LogFile(context, file_prefix="console", title="Console")
        self._listeners: list[tuple[Any, str, Any]] = []
        self._initialized = context.track_task(asyncio.create_task(self._initialize()))
        self._add_listener(page, "console", self._on_console_message)
        self._add_listener(page, "pageerror", self._on_page_error)
        self._add_listener(page, "request", self._on_request)
        self._add_listener(page, "response", self._on_response)
        self._add_listener(page, "requestfailed", self._on_request_failed)
        self._add_listener(page, "dialog", self._on_dialog)
        self._add_listener(page, "filechooser", self._on_file_chooser)
        self._add_listener(page, "download", self._on_download)

    @property
    def action_timeout(self) -> int | None:
        return self.context.config.action_timeout

    @property
    def navigation_timeout(self) -> int | None:
        return self.context.config.navigation_timeout

    async def dispose(self) -> None:
        for target, event, handler in self._listeners:
            with suppress(Exception):
                target.remove_listener(event, handler)
        self._listeners.clear()
        self._console_log.stop()

    async def close(self) -> None:
        await self.page.close()

    def log_error_message(self, text: str) -> None:
        entry = ConsoleEntry(
            type="error",
            text=text,
            location_url=self.page.url,
            navigation_index=self._navigation_index,
        )
        self._console_messages.append(entry)
        self._add_log_entry({"type": "console", "message": entry})
        self._append_console_log(entry)

    async def navigate(self, url: str) -> None:
        await self._initialized
        self._clear_collected_artifacts()
        download_event: asyncio.Future[Download] = (
            asyncio.get_running_loop().create_future()
        )

        def download_listener(download: Download) -> None:
            if not download_event.done():
                download_event.set_result(download)

        self.page.on("download", download_listener)
        try:
            commit_timeout = self.navigation_timeout
            if commit_timeout is not None:
                commit_timeout = min(commit_timeout, _COMMIT_ACK_TIMEOUT_MS)
            await self.page.goto(
                url,
                wait_until="commit",
                timeout=commit_timeout,
            )
        except PlaywrightTimeoutError:
            if not _same_navigation_target(self.page.url, url):
                with suppress(Error):
                    await self.page.evaluate("window.stop()")
                raise
        except Error as exc:
            if _might_be_download_error(exc):
                try:
                    await asyncio.wait_for(download_event, timeout=3)
                except TimeoutError:
                    raise exc from None
                await asyncio.sleep(0.5)
                return
            if not (
                _is_aborted_navigation_error(exc)
                and _same_navigation_target(self.page.url, url)
            ):
                raise
            # The document committed to the requested URL but the protocol
            # reported an abort (Firefox/Camoufox NS_ERROR_ABORT, often a race
            # with redirecting sites). The navigation did land; fall through to
            # the DOM settle wait below.
        finally:
            self.page.remove_listener("download", download_listener)
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Error:
            pass

    async def check_url_and_navigate(self, url: str) -> str:
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                if url.startswith("localhost"):
                    url = "http://" + url
                else:
                    url = "https://" + url
        except Exception:
            if url.startswith("localhost"):
                url = "http://" + url
            else:
                url = "https://" + url
        self.context._check_url_allowed(url)
        await self.navigate(url)
        return url

    async def go_back(self) -> None:
        await self.page.go_back(wait_until="commit", timeout=self.navigation_timeout)

    async def go_forward(self) -> None:
        await self.page.go_forward(wait_until="commit", timeout=self.navigation_timeout)

    async def reload(self) -> None:
        await self.page.reload(timeout=self.navigation_timeout)

    async def resize(self, *, width: int, height: int) -> None:
        await self.page.set_viewport_size({"width": width, "height": height})

    async def click(
        self,
        resolved: ResolvedTarget,
        *,
        double_click: bool = False,
        button: Button | None = None,
        modifiers: list[Modifier] | None = None,
    ) -> None:
        async def action() -> None:
            if double_click:
                await resolved.locator.dblclick(
                    button=button, modifiers=modifiers, timeout=self.action_timeout
                )
            else:
                await resolved.locator.click(
                    button=button, modifiers=modifiers, timeout=self.action_timeout
                )

        await self.wait_for_completion(action)

    async def select_option(
        self, resolved: ResolvedTarget, *, values: list[str]
    ) -> None:
        await resolved.locator.select_option(values, timeout=self.action_timeout)

    async def hover(self, resolved: ResolvedTarget) -> None:
        await resolved.locator.hover(timeout=self.action_timeout)

    async def drag_to(self, start: ResolvedTarget, end: ResolvedTarget) -> None:
        await self.wait_for_completion(
            lambda: start.locator.drag_to(end.locator, timeout=self.action_timeout)
        )

    async def mouse_move_xy(self, *, x: float, y: float) -> None:
        await self.page.mouse.move(x, y)

    async def mouse_click_xy(
        self,
        *,
        x: float,
        y: float,
        button: Button | None = None,
        click_count: int | None = None,
        delay: float | None = None,
    ) -> None:
        await self.wait_for_completion(
            lambda: self.page.mouse.click(
                x, y, button=button, click_count=click_count, delay=delay
            )
        )

    async def mouse_down(self, *, button: Button | None = None) -> None:
        await self.page.mouse.down(button=button)

    async def mouse_up(self, *, button: Button | None = None) -> None:
        await self.page.mouse.up(button=button)

    async def mouse_wheel(self, *, delta_x: float, delta_y: float) -> None:
        await self.page.mouse.wheel(delta_x, delta_y)

    async def mouse_drag_xy(
        self,
        *,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        async def action() -> None:
            await self.page.mouse.move(start_x, start_y)
            await self.page.mouse.down()
            await self.page.mouse.move(end_x, end_y)
            await self.page.mouse.up()

        await self.wait_for_completion(action)

    async def wait_for_completion(self, action):
        await self._initialized
        if self._modal_states:
            return
        self._modal_event = asyncio.Event()
        requests: list[Request] = []

        def request_listener(request: Request) -> None:
            requests.append(request)

        async def action_and_settle():
            self.page.on("request", request_listener)
            try:
                result = await action()
                await self.wait_for_timeout(0.5)
            finally:
                self.page.remove_listener("request", request_listener)

            if any(request.is_navigation_request() for request in requests):
                try:
                    await self.page.main_frame.wait_for_load_state(
                        "load", timeout=10000
                    )
                except Error:
                    pass
                return result

            response_tasks = [
                asyncio.create_task(_wait_for_request_response(request))
                for request in requests
            ]
            if response_tasks:
                done, pending = await asyncio.wait(response_tasks, timeout=5)
                for task in pending:
                    task.cancel()
                for task in done:
                    _consume_task_exception(task)
                await self.wait_for_timeout(0.5)
            return result

        action_task = self.context.track_task(asyncio.create_task(action_and_settle()))
        modal_task = self.context.track_task(
            asyncio.create_task(self._modal_event.wait())
        )
        done, pending = await asyncio.wait(
            {action_task, modal_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if action_task in done:
            modal_task.cancel()
            return await action_task
        else:
            action_task.add_done_callback(
                lambda task: task.exception() if not task.cancelled() else None
            )
            return None

    async def press_key(self, key: str) -> None:
        if key == "Enter":
            await self.wait_for_completion(lambda: self.page.keyboard.press(key))
        else:
            await self.page.keyboard.press(key)

    async def press_sequentially(self, *, text: str, submit: bool = False) -> None:
        await self.page.keyboard.type(text)
        if submit:
            await self.wait_for_completion(lambda: self.page.keyboard.press("Enter"))

    async def key_down(self, key: str) -> None:
        await self.page.keyboard.down(key)

    async def key_up(self, key: str) -> None:
        await self.page.keyboard.up(key)

    async def type_text(
        self,
        resolved: ResolvedTarget,
        *,
        text: str,
        submit: bool = False,
        slowly: bool = False,
    ) -> None:
        async def action() -> None:
            if slowly:
                await resolved.locator.press_sequentially(
                    text, timeout=self.action_timeout
                )
            else:
                await resolved.locator.fill(text, timeout=self.action_timeout)
            if submit:
                await resolved.locator.press("Enter", timeout=self.action_timeout)

        if submit or slowly:
            await self.wait_for_completion(action)
        else:
            await action()

    async def fill_form_field(
        self, resolved: ResolvedTarget, *, field_type: str, value: str
    ) -> None:
        if field_type in {"textbox", "slider"}:
            await self._fill_text_field(resolved.locator, value)
        elif field_type in {"checkbox", "radio"}:
            await resolved.locator.set_checked(
                value == "true", timeout=self.action_timeout
            )
        elif field_type == "combobox":
            await resolved.locator.select_option(
                label=value, timeout=self.action_timeout
            )
        else:
            raise ValueError(f"Unsupported form field type: {field_type}")

    async def _fill_text_field(self, locator: Any, value: str) -> None:
        """Replace a text input's value using only the Playwright API.

        ``locator.fill()`` on the camoufox (Firefox) backend appends to the
        existing value of simplify's controlled input instead of replacing it
        (measured 1x, 2x, 3x copies on three identical fills), which corrupts
        fields and makes the page signature churn so loop guards cannot fire.
        Clearing the field first with ``locator.clear()`` (select-all + delete)
        and only then filling yields exactly one copy of the value every time.
        """
        await locator.clear(timeout=self.action_timeout)
        await locator.fill(value, timeout=self.action_timeout)

    async def check(self, resolved: ResolvedTarget) -> None:
        await resolved.locator.check(timeout=self.action_timeout)

    async def uncheck(self, resolved: ResolvedTarget) -> None:
        await resolved.locator.uncheck(timeout=self.action_timeout)

    async def evaluate(
        self, expression: str, resolved: ResolvedTarget | None = None
    ) -> tuple[Any, bool, bool]:
        if resolved is not None:
            result = await resolved.locator.evaluate(
                """async (element, expr) => {
                    const value = eval(`(${expr})`);
                    const isFunction = typeof value === 'function';
                    const result = await (isFunction ? value(element) : value);
                    return { result: result === undefined ? null : result, isFunction, isUndefined: result === undefined };
                }""",
                expression,
            )
        else:
            result = await self.page.evaluate(
                """async expr => {
                    const value = eval(`(${expr})`);
                    const isFunction = typeof value === 'function';
                    const result = await (isFunction ? value() : value);
                    return { result: result === undefined ? null : result, isFunction, isUndefined: result === undefined };
                }""",
                expression,
            )
        return result["result"], result["isFunction"], result["isUndefined"]

    async def capture_snapshot(
        self,
        *,
        target: str | None = None,
        root: Locator | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
    ) -> str:
        return (
            await self.capture_tab_snapshot(target=target, depth=depth, boxes=boxes)
        ).aria_snapshot

    async def capture_tab_snapshot(
        self,
        *,
        target: str | None = None,
        root: Locator | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
        relative_to: Path | None = None,
        include_aria: bool = True,
    ) -> TabSnapshot:
        await self._initialized
        if self._modal_states:
            return TabSnapshot(
                aria_snapshot="",
                modal_states=list(self._modal_states),
                events=[],
                console_link=None,
            )
        aria_snapshot = ""
        if include_aria:
            aria_snapshot = await self._aria_snapshot_race(
                target=target, root=root, depth=depth, boxes=boxes
            )
            if self._modal_states:
                return TabSnapshot(
                    aria_snapshot="",
                    modal_states=list(self._modal_states),
                    events=[],
                    console_link=None,
                )
        snapshot = TabSnapshot(
            aria_snapshot=aria_snapshot,
            modal_states=list(self._modal_states),
            events=self._recent_event_entries,
            console_link=await self._console_log.take(relative_to=relative_to),
        )
        self._recent_event_entries = []
        return snapshot

    async def header_snapshot(self) -> TabHeader:
        await self._initialized
        title = "" if self.crashed else await self._title_or_empty()
        header = TabHeader(
            title=title,
            url=self.page.url,
            current=self.context.current_tab() is self,
            crashed=self.crashed,
            console=await self.console_message_count(),
            main_document_status=self._main_document_status,
        )
        header.changed = header != self._last_header
        self._last_header = TabHeader(
            title=header.title,
            url=header.url,
            current=header.current,
            crashed=header.crashed,
            console=dict(header.console),
            main_document_status=header.main_document_status,
        )
        return header

    async def render_page_markdown(self) -> list[str]:
        await self._initialized
        lines = [f"- Page URL: {self.page.url}"]
        title = await self.page.title()
        if title:
            lines.append(f"- Page Title: {title}")
        return lines

    async def resolve_target(
        self, *, target: str, element: str | None = None
    ) -> ResolvedTarget:
        if not _REF_PATTERN.match(target):
            selector = locator_or_selector_as_selector(
                target, test_id_attribute=self.context.config.test_id_attribute
            )
            handle = await self.page.query_selector(selector)
            if handle is None:
                raise ValueError(f'"{target}" does not match any elements.')
            await handle.dispose()
            return ResolvedTarget(
                locator=self.page.locator(selector),
                code=as_python_locator(selector),
            )

        try:
            locator = self.page.locator(f"aria-ref={target}")
            if element:
                locator = locator.describe(element)
            normalized = await locator.normalize()
            return ResolvedTarget(
                locator=locator,
                # Uses private _impl_obj because Playwright Python does not expose a
                # public `selector` property on normalized locators yet.
                code=as_python_locator(normalized._impl_obj._selector),
            )
        except Exception as exc:
            raise ValueError(
                f"Ref {target} not found in the current page snapshot. Try capturing new snapshot."
            ) from exc

    async def snapshot_locator(self, target: str | None) -> Locator:
        if target is None:
            raise ValueError(
                "Full-page snapshots use page.aria_snapshot(); no locator is available."
            )
        return (await self.resolve_target(target=target)).locator

    async def console_message_count(self) -> dict[str, int]:
        messages = await self._console_entries(all_messages=False)
        return {
            "total": len(messages),
            "errors": sum(message.type == "error" for message in messages),
            "warnings": sum(message.type == "warning" for message in messages),
        }

    async def console_messages(
        self, *, level: str = "info", all_messages: bool = False
    ) -> list[str]:
        return [
            message.render()
            for message in await self._console_entries(all_messages=all_messages)
            if _should_include_console_message(level, message.type)
        ]

    def requests(self) -> list[Request]:
        return [entry.request for entry in self._requests]

    def request_entries(self) -> list[RequestEntry]:
        return list(self._requests)

    def modal_states(self) -> list[dict[str, Any]]:
        return self._modal_states

    def clear_modal_state(self, modal_state: dict[str, Any]) -> None:
        self._modal_states = [
            state for state in self._modal_states if state is not modal_state
        ]

    async def prune_stale_dialogs(self) -> None:
        """Drop recorded dialog modal states whose native dialog is already closed.

        A recorded dialog can be dismissed by the human directly in the
        visible browser instead of through browser_handle_dialog. Playwright
        never notifies us in that case, so without a liveness probe the stale
        state would block every tool forever. While a native dialog is still
        open the page's JavaScript is suspended, so a short evaluate probe
        completes only when the dialog is gone.
        """
        if not any(state.get("type") == "dialog" for state in self._modal_states):
            return
        try:
            await asyncio.wait_for(self.page.evaluate("1 + 1"), timeout=0.5)
        except Exception:
            return
        self._modal_states = [
            state for state in self._modal_states if state.get("type") != "dialog"
        ]
        self._modal_event = asyncio.Event()

    def clear_requests(self) -> None:
        self._requests.clear()

    async def clear_console_messages(self) -> None:
        await self._initialized
        self._console_messages.clear()
        with suppress(Error):
            await self.page.clear_console_messages()
        with suppress(Error):
            await self.page.clear_page_errors()
        self._console_log.stop()
        self._console_log = LogFile(
            self.context, file_prefix="console", title="Console"
        )

    async def _console_entries(self, *, all_messages: bool) -> list[ConsoleEntry]:
        filter_value: Literal["all", "since-navigation"] = (
            "all" if all_messages else "since-navigation"
        )
        try:
            messages = await self.page.console_messages(filter=filter_value)
            errors = await self.page.page_errors(filter=filter_value)
        except (AttributeError, Error):
            if all_messages:
                return list(self._console_messages)
            return [
                message
                for message in self._console_messages
                if message.navigation_index == self._navigation_index
            ]
        entries = [self._console_entry_from_message(message) for message in messages]
        entries.extend(self._console_entry_from_page_error(error) for error in errors)
        return entries

    def _clear_collected_artifacts(self) -> None:
        self._navigation_index += 1
        self._requests.clear()
        self._recent_event_entries.clear()
        self._main_document_status = None
        self._console_log.stop()
        self._console_log = LogFile(
            self.context, file_prefix="console", title="Console"
        )

    def _on_console_message(self, message: ConsoleMessage) -> None:
        entry = self._console_entry_from_message(message)
        self._console_messages.append(entry)
        self._add_log_entry({"type": "console", "message": entry})
        self._append_console_log(entry)

    def _on_page_error(self, error: Error) -> None:
        entry = self._console_entry_from_page_error(error)
        self._console_messages.append(entry)
        self._add_log_entry({"type": "console", "message": entry})
        self._append_console_log(entry)

    def _console_entry_from_message(self, message: ConsoleMessage) -> ConsoleEntry:
        location = message.location
        line_number = location.get("lineNumber")
        fallback_line: int | None = None
        if not line_number:
            # Some console message sources report the line under a non-typed
            # "line" key; keep the fallback but only accept an int.
            fallback = location.get("line")
            fallback_line = fallback if isinstance(fallback, int) else None
        return ConsoleEntry(
            type=message.type,
            text=message.text,
            location_url=location.get("url") or None,
            location_line=line_number or fallback_line,
            navigation_index=self._navigation_index,
        )

    def _console_entry_from_page_error(self, error: Error) -> ConsoleEntry:
        text = (
            getattr(error, "stack", None)
            or getattr(error, "message", None)
            or str(error)
        )
        return ConsoleEntry(
            type="error",
            text=str(text),
            location_url=self.page.url,
            navigation_index=self._navigation_index,
        )

    def _on_request(self, request: Request) -> None:
        self._requests.append(RequestEntry(request=request))
        self._add_log_entry({"type": "request", "request": request})

    def _on_response(self, response: PlaywrightResponse) -> None:
        request = response.request
        self._request_entry(request).response = response
        if _is_main_frame_navigation(self.page, request) and not _is_redirect(response):
            self._main_document_status = DocumentStatus(
                status=response.status,
                status_text=response.status_text,
            )
        self._add_log_entry({"type": "request", "request": request})

    def _on_request_failed(self, request: Request) -> None:
        self._request_entry(request).failure = request.failure or "Unknown error"
        self._add_log_entry({"type": "request", "request": request})

    def _request_entry(self, request: Request) -> RequestEntry:
        for entry in reversed(self._requests):
            if entry.request is request:
                return entry
        entry = RequestEntry(request=request)
        self._requests.append(entry)
        return entry

    def _on_dialog(self, dialog: Dialog) -> None:
        self._modal_states.append(
            {
                "type": "dialog",
                "description": f'"{dialog.type}" dialog with message "{dialog.message}"',
                "dialog": dialog,
                "clearedBy": {
                    "tool": "browser_handle_dialog",
                    "skill": "dialog-accept or dialog-dismiss",
                },
            }
        )
        self._modal_event.set()

    def _on_file_chooser(self, file_chooser: FileChooser) -> None:
        self._modal_states.append(
            {
                "type": "fileChooser",
                "description": "File chooser",
                "fileChooser": file_chooser,
                "clearedBy": {"tool": "browser_file_upload", "skill": "upload"},
            }
        )
        self._modal_event.set()

    def _on_download(self, download: Download) -> None:
        import asyncio

        self.context.track_task(asyncio.create_task(self._download_started(download)))

    async def liveness(self, timeout_seconds: float = 2.0) -> bool:
        """Return True when the renderer answers CDP within the timeout.

        A page whose main thread is blocked (stuck synchronous request,
        frozen renderer) fails this probe within the timeout instead of
        hanging snapshot/title/query callers indefinitely.
        """
        if self._modal_states:
            return False
        try:
            async with asyncio.timeout(timeout_seconds):
                await self.page.evaluate("1")
            return True
        except (TimeoutError, Error):
            return False

    async def _title_or_empty(self) -> str:
        if self._modal_states:
            return ""

        async def _title_with_bound() -> str:
            async with asyncio.timeout(5):
                return await self.page.title()
            raise Error("title timeout")

        title_task = self.context.track_task(asyncio.create_task(_title_with_bound()))
        modal_task = self.context.track_task(
            asyncio.create_task(self._modal_event.wait())
        )
        done, pending = await asyncio.wait(
            {title_task, modal_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if modal_task in done:
            return ""
        try:
            return await title_task
        except Error:
            return ""

    async def _download_started(self, download: Download) -> None:
        from .context import FilenameTemplate

        suggested_filename = sanitize_for_file_path(download.suggested_filename)
        output_file = await self.context.output_file(
            FilenameTemplate(
                prefix="download",
                ext="bin",
                suggested_filename=suggested_filename,
            ),
            origin="code",
        )
        self._add_log_entry(
            {"type": "download-start", "suggested_filename": suggested_filename}
        )
        await download.save_as(output_file)
        self._add_log_entry(
            {
                "type": "download-finish",
                "suggested_filename": suggested_filename,
                "output_file": output_file,
            }
        )

    def _add_log_entry(self, entry: dict[str, Any]) -> None:
        self._recent_event_entries.append(entry)

    def _append_console_log(self, entry: ConsoleEntry) -> None:
        import asyncio
        import time

        if not _should_include_console_message(
            self.context.config.console_level, entry.type
        ):
            return
        self.context.track_task(
            asyncio.create_task(
                self._console_log.append_line(time.time() * 1000, entry.render())
            )
        )

    def _add_listener(self, target: Any, event: str, handler: Any) -> None:
        target.on(event, handler)
        self._listeners.append((target, event, handler))

    async def _initialize(self) -> None:
        messages = await self.page.console_messages(filter="all")
        for message in messages:
            self._on_console_message(message)
        errors = await self.page.page_errors(filter="all")
        for error in errors:
            self._on_page_error(error)
        requests = await self.page.requests()
        for request in requests:
            if request.existing_response is not None or request.failure is not None:
                self._requests.append(
                    RequestEntry(
                        request=request,
                        response=request.existing_response,
                        failure=request.failure,
                    )
                )
        await self.context.run_init_pages(self.page)

    async def _aria_snapshot_race(
        self,
        *,
        target: str | None,
        root: Locator | None,
        depth: int | None,
        boxes: bool | None,
    ) -> str:
        if self._modal_states:
            return ""

        async def capture() -> str:
            try:
                async with asyncio.timeout(_ARIA_SNAPSHOT_TIMEOUT_SECONDS):
                    if root is not None:
                        snapshot = root.aria_snapshot
                        return await snapshot(
                            **_aria_snapshot_options(snapshot, depth=depth, boxes=boxes)
                        )
                    if target is None:
                        snapshot = self.page.aria_snapshot
                        return await snapshot(
                            **_aria_snapshot_options(snapshot, depth=depth, boxes=boxes)
                        )
                    locator = await self.snapshot_locator(target)
                    snapshot = locator.aria_snapshot
                    return await snapshot(
                        **_aria_snapshot_options(snapshot, depth=depth, boxes=boxes)
                    )
            except TimeoutError:
                return ""
            raise

        capture_task = self.context.track_task(asyncio.create_task(capture()))
        modal_task = self.context.track_task(
            asyncio.create_task(self._modal_event.wait())
        )
        done, pending = await asyncio.wait(
            {capture_task, modal_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        if modal_task in done:
            return ""
        snapshot = await capture_task
        if not snapshot:
            return ""
        return snapshot

    async def wait_for_timeout(self, seconds: float) -> None:
        if any(state.get("type") == "dialog" for state in self._modal_states):
            await asyncio.sleep(seconds)
            return
        try:
            await self.page.evaluate(
                "(ms) => new Promise((resolve) => setTimeout(resolve, ms))",
                max(0, int(seconds * 1000)),
            )
        except Error:
            await asyncio.sleep(seconds)


_CONSOLE_MESSAGE_LEVELS = ["error", "warning", "info", "debug"]


def _aria_snapshot_options(
    snapshot: Any,
    *,
    depth: int | None,
    boxes: bool | None,
) -> dict[str, Any]:
    options: dict[str, Any] = {"mode": "ai", "depth": depth}
    if "boxes" in inspect.signature(snapshot).parameters:
        options["boxes"] = boxes
    return options


def _same_navigation_target(actual: str, requested: str) -> bool:
    """Confirm that a timed-out protocol navigation reached its requested URL."""
    actual_url = urlparse(actual)
    requested_url = urlparse(requested)
    return (
        actual_url.scheme.lower(),
        actual_url.netloc.lower(),
        actual_url.path or "/",
        actual_url.params,
        actual_url.query,
    ) == (
        requested_url.scheme.lower(),
        requested_url.netloc.lower(),
        requested_url.path or "/",
        requested_url.params,
        requested_url.query,
    )


def _console_level_for_message_type(message_type: str) -> str:
    if message_type in ("assert", "error"):
        return "error"
    if message_type == "warning":
        return "warning"
    if message_type in (
        "count",
        "dir",
        "dirxml",
        "info",
        "log",
        "table",
        "time",
        "timeEnd",
    ):
        return "info"
    if message_type in (
        "clear",
        "debug",
        "endGroup",
        "profile",
        "profileEnd",
        "startGroup",
        "startGroupCollapsed",
        "trace",
    ):
        return "debug"
    return "info"


_ARIA_SNAPSHOT_TIMEOUT_SECONDS = 30.0


def _should_include_console_message(level: str, message_type: str) -> bool:
    message_level = _console_level_for_message_type(message_type)
    threshold = level or "info"
    return _CONSOLE_MESSAGE_LEVELS.index(
        message_level
    ) <= _CONSOLE_MESSAGE_LEVELS.index(threshold)


async def _wait_for_request_response(request: Request) -> None:
    try:
        response = await request.response()
        if response is not None and request.resource_type in {
            "document",
            "stylesheet",
            "script",
            "xhr",
            "fetch",
        }:
            async with asyncio.timeout(10):
                await response.finished()
    except (Error, TimeoutError):
        return


def _consume_task_exception(task: asyncio.Task[Any]) -> None:
    """Consume a settle-watcher task exception without re-raising it.

    The action itself has already completed at this point, so a watcher
    failure must never turn a successful browser action into a reported
    failure. Mirrors the upstream server, which swallows every watcher
    rejection with .catch(() => {}).
    """
    if task.cancelled():
        return
    try:
        exception = task.exception()
    except asyncio.CancelledError:
        return
    if exception is not None:
        logger.warning("Settle watcher failed after a completed action: %s", exception)


def _might_be_download_error(error: Error) -> bool:
    message = str(error)
    return "net::ERR_ABORTED" in message or "Download is starting" in message


def _is_aborted_navigation_error(error: Error) -> bool:
    """Detect a Firefox/Camoufox abort that can race a committed navigation."""
    return "NS_ERROR_ABORT" in str(error)


def _is_main_frame_navigation(page: Page, request: Request) -> bool:
    try:
        return request.is_navigation_request() and request.frame is page.main_frame
    except Error:
        return False


def _is_redirect(response: PlaywrightResponse) -> bool:
    return 300 <= response.status <= 399
