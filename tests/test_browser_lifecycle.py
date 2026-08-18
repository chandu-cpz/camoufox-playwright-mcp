from __future__ import annotations

import asyncio
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from camoufox_playwright_mcp.backend import context as context_module
from camoufox_playwright_mcp.backend.browser_backend import BrowserBackend
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tab import Tab, _aria_snapshot_options
from camoufox_playwright_mcp.backend.tool import Tool
from camoufox_playwright_mcp.backend.tools.common import common_tools
from camoufox_playwright_mcp.mcp.config import load_config


def _config(**options: Any):
    return load_config(
        browser=options.pop("browser", None),
        caps="",
        config_path=options.pop("config_path", None),
        headless=options.pop("headless", True),
        test_id_attribute="data-testid",
        vision=False,
        **options,
    )


def test_aria_snapshot_options_omit_unsupported_boxes() -> None:
    async def snapshot(*, mode: str, depth: int | None) -> str:
        return f"{mode}:{depth}"

    assert _aria_snapshot_options(snapshot, depth=4, boxes=True) == {
        "mode": "ai",
        "depth": 4,
    }


def test_aria_snapshot_options_preserve_supported_boxes() -> None:
    async def snapshot(*, mode: str, depth: int | None, boxes: bool | None) -> str:
        return f"{mode}:{depth}:{boxes}"

    assert _aria_snapshot_options(snapshot, depth=4, boxes=True) == {
        "mode": "ai",
        "depth": 4,
        "boxes": True,
    }


def test_navigation_releases_after_commit_and_only_briefly_waits_for_dom() -> None:
    class NavigationPage:
        def __init__(self) -> None:
            self.goto_options: dict[str, Any] = {}
            self.load_options: tuple[str, int] | None = None
            self.url = "about:blank"

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **options: Any) -> None:
            self.goto_options = options

        async def wait_for_load_state(self, state: str, *, timeout: int) -> None:
            self.load_options = (state, timeout)

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 60_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        tab = NavigationTab()
        await Tab.navigate(cast(Any, tab), "https://example.com")
        assert tab.page.goto_options == {"wait_until": "commit", "timeout": 60_000}
        assert tab.page.load_options == ("domcontentloaded", 5000)

    asyncio.run(run())


def test_navigation_allows_slow_profiles_up_to_two_minutes() -> None:
    class NavigationPage:
        url = "about:blank"

        def __init__(self) -> None:
            self.goto_options: dict[str, Any] = {}

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **options: Any) -> None:
            self.goto_options = options

        async def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
            assert timeout == 5000

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 180_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        tab = NavigationTab()
        await Tab.navigate(cast(Any, tab), "https://example.com")
        assert tab.page.goto_options == {"wait_until": "commit", "timeout": 120_000}

    asyncio.run(run())


def test_navigation_accepts_requested_url_when_commit_event_is_missing() -> None:
    class NavigationPage:
        url = "https://example.com/jobs?id=42"

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **_options: Any) -> None:
            raise PlaywrightTimeoutError("commit event was not emitted")

        async def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
            assert timeout == 5000

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 60_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        await Tab.navigate(cast(Any, NavigationTab()), "https://example.com/jobs?id=42")

    asyncio.run(run())


def test_navigation_accepts_abort_when_document_already_committed() -> None:
    class NavigationPage:
        url = "https://example.com/applications/new"

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **_options: Any) -> None:
            raise PlaywrightError("Page.goto: NS_ERROR_ABORT")

        async def wait_for_load_state(self, _state: str, *, timeout: int) -> None:
            assert timeout == 5000

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 60_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        # The document already committed to the requested URL before the
        # protocol reported the abort; navigation must not hard-fail.
        await Tab.navigate(cast(Any, NavigationTab()), "https://example.com/applications/new")

    asyncio.run(run())


def test_navigation_reraises_abort_when_target_was_not_committed() -> None:
    class NavigationPage:
        url = "about:blank"

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **_options: Any) -> None:
            raise PlaywrightError("Page.goto: NS_ERROR_ABORT")

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 60_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        with pytest.raises(PlaywrightError):
            await Tab.navigate(cast(Any, NavigationTab()), "https://example.com/applications/new")

    asyncio.run(run())


def test_navigation_stops_uncommitted_load_before_reraising_timeout() -> None:
    class NavigationPage:
        url = "about:blank"

        def __init__(self) -> None:
            self.evaluated: list[str] = []

        def on(self, _event: str, _listener: Any) -> None:
            pass

        def remove_listener(self, _event: str, _listener: Any) -> None:
            pass

        async def goto(self, _url: str, **_options: Any) -> None:
            raise PlaywrightTimeoutError("commit event was not emitted")

        async def evaluate(self, expression: str) -> None:
            self.evaluated.append(expression)

    class NavigationTab:
        def __init__(self) -> None:
            loop = asyncio.get_running_loop()
            self._initialized = loop.create_future()
            self._initialized.set_result(None)
            self.page = NavigationPage()
            self.navigation_timeout = 60_000

        def _clear_collected_artifacts(self) -> None:
            pass

    async def run() -> None:
        tab = NavigationTab()
        with pytest.raises(PlaywrightTimeoutError):
            await Tab.navigate(cast(Any, tab), "https://example.com")
        assert tab.page.evaluated == ["window.stop()"]

    asyncio.run(run())


def test_default_launch_uses_persistent_context(monkeypatch, tmp_path: Path) -> None:
    async def run() -> None:
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
        backend = BrowserBackend(_config(browser="chromium"), [])
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        await backend._launch_browser()

        assert playwright.chromium.persistent_user_data_dir is not None
        assert "ms-playwright-mcp" in str(playwright.chromium.persistent_user_data_dir)
        assert playwright.chromium.launch_called is False
        assert playwright.chromium.persistent_options["handle_sigint"] is False
        assert playwright.chromium.persistent_options["handle_sigterm"] is False
        assert playwright.chromium.persistent_options["ignore_default_args"] == ["--disable-extensions"]

    asyncio.run(run())


def test_isolated_launch_uses_ephemeral_browser() -> None:
    async def run() -> None:
        backend = BrowserBackend(_config(browser="chromium", isolated=True), [])
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        await backend._launch_browser()

        assert playwright.chromium.launch_called is True
        assert playwright.chromium.persistent_user_data_dir is None

    asyncio.run(run())


def test_camoufox_default_launch_uses_persistent_context(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []

    async def async_new_browser(playwright: Any, **options: Any) -> object:
        calls.append({"playwright": playwright, **options})
        return FakePersistentContext()

    async_api = types.ModuleType("camoufox.async_api")
    setattr(async_api, "AsyncNewBrowser", async_new_browser)
    camoufox = types.ModuleType("camoufox")
    monkeypatch.setitem(sys.modules, "camoufox", camoufox)
    monkeypatch.setitem(sys.modules, "camoufox.async_api", async_api)

    async def run() -> None:
        monkeypatch.setenv("PWMCP_PROFILES_DIR_FOR_TEST", str(tmp_path / "profiles"))
        backend = BrowserBackend(
            _config(
                browser="camoufox",
                headless=True,
                config_path=None,
            ),
            [],
        )
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        browser = await backend._launch_browser(tmp_path)

        assert browser is FakePersistentContext.browser
        assert len(calls) == 1
        assert calls[0]["playwright"] is playwright
        assert calls[0]["persistent_context"] is True
        assert Path(calls[0]["user_data_dir"]).name.startswith("mcp-camoufox-")
        assert calls[0]["headless"] is True
        assert calls[0]["handle_sigint"] is False
        assert calls[0]["handle_sigterm"] is False

    asyncio.run(run())


def test_camoufox_isolated_launch_uses_non_persistent_browser(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict[str, Any]] = []
    fake_browser = object()

    async def async_new_browser(playwright: Any, **options: Any) -> object:
        calls.append({"playwright": playwright, **options})
        return fake_browser

    async_api = types.ModuleType("camoufox.async_api")
    setattr(async_api, "AsyncNewBrowser", async_new_browser)
    camoufox = types.ModuleType("camoufox")
    monkeypatch.setitem(sys.modules, "camoufox", camoufox)
    monkeypatch.setitem(sys.modules, "camoufox.async_api", async_api)

    async def run() -> None:
        backend = BrowserBackend(
            _config(
                browser="camoufox",
                isolated=True,
                headless=True,
                config_path=None,
            ),
            [],
        )
        playwright = FakePlaywright()
        backend._playwright = cast(Any, playwright)

        browser = await backend._launch_browser(tmp_path)

        assert browser is fake_browser
        assert len(calls) == 1
        assert calls[0]["playwright"] is playwright
        assert calls[0]["persistent_context"] is False
        assert "user_data_dir" not in calls[0]
        assert calls[0]["headless"] is True

    asyncio.run(run())


def test_unexpected_tool_error_does_not_close_browser_backend() -> None:
    async def broken_handler(_context: Any, _params: dict[str, Any], _response: Any) -> None:
        raise RuntimeError("boom")

    async def run() -> None:
        backend = ErrorBackend(_config(), [Tool(name="browser_broken", capability="core", handler=broken_handler)])

        result = await backend.call_tool("browser_broken", {})

        assert result.is_error is True
        assert "boom" in result.content[0].text
        assert backend.closed is False

    asyncio.run(run())


def test_browser_close_does_not_prevent_next_tool_call() -> None:
    async def probe_handler(_context: Context, _params: dict[str, Any], response: Response) -> None:
        response.add_text_result("alive")

    async def run() -> None:
        backend = ErrorBackend(
            _config(),
            [*common_tools, Tool(name="browser_probe", capability="core", handler=probe_handler)],
        )

        close_result = await backend.call_tool("browser_close", {})
        next_result = await backend.call_tool("browser_probe", {})

        assert backend.closed is True
        assert close_result.meta == {"isClose": True}
        assert next_result.content[0].text == "### Result\nalive"

    asyncio.run(run())


def test_disconnected_backend_marks_result_as_close() -> None:
    async def probe_handler(_context: Context, _params: dict[str, Any], response: Response) -> None:
        response.add_text_result("alive")

    async def run() -> None:
        backend = ErrorBackend(_config(), [Tool(name="browser_probe", capability="core", handler=probe_handler)])
        backend._disconnected = True

        result = await backend.call_tool("browser_probe", {})

        assert result.meta == {"isClose": True}

    asyncio.run(run())


def test_context_initialize_tracks_existing_and_future_pages() -> None:
    async def run() -> None:
        existing_page = FakePage("existing")
        browser_context = FakeBrowserContext([existing_page])
        context = Context(cast(Any, browser_context), _config())

        await context.initialize()
        future_page = FakePage("future")
        browser_context.emit_page(future_page)

        assert [tab.page for tab in context.tabs()] == [existing_page, future_page]
        current_tab = context.current_tab()
        assert current_tab is not None
        assert current_tab.page is existing_page

    asyncio.run(run())


def test_context_new_tab_uses_page_event_without_double_registering() -> None:
    async def run() -> None:
        browser_context = FakeBrowserContext([])
        context = Context(cast(Any, browser_context), _config())
        await context.initialize()

        tab = await context.new_tab()

        assert context.tabs() == [tab]
        assert context.current_tab() is tab

    asyncio.run(run())


def test_context_select_tab_survives_unacknowledged_foregrounding(monkeypatch: Any) -> None:
    class HangingPage(FakePage):
        async def bring_to_front(self) -> None:
            await asyncio.Event().wait()

    async def run() -> None:
        first_page = FakePage("first")
        hanging_page = HangingPage("hanging")
        browser_context = FakeBrowserContext([first_page, hanging_page])
        context = Context(cast(Any, browser_context), _config())
        await context.initialize()
        monkeypatch.setattr(context_module, "_BRING_TO_FRONT_TIMEOUT_SECONDS", 0.01)

        await context.select_tab(1)

        current_tab = context.current_tab()
        assert current_tab is not None
        assert current_tab.page is hanging_page

    asyncio.run(run())


def test_context_video_recording_tracks_existing_and_future_pages(tmp_path: Path) -> None:
    async def run() -> None:
        existing_page = FakePage("existing")
        browser_context = FakeBrowserContext([existing_page])
        context = Context(cast(Any, browser_context), _config(), cwd=tmp_path)

        await context.initialize()
        await context.start_video_recording(tmp_path / "video.webm", {"size": {"width": 640, "height": 480}})

        future_page = FakePage("future")
        browser_context.pages.append(future_page)
        browser_context.emit_page(future_page)
        await asyncio.sleep(0)

        file_names = await context.stop_video_recording()

        assert existing_page.screencast.started == [(tmp_path / "video.webm", {"width": 640, "height": 480})]
        assert future_page.screencast.started == [(tmp_path / "video-1.webm", {"width": 640, "height": 480})]
        assert existing_page.screencast.stopped == 1
        assert future_page.screencast.stopped == 1
        assert file_names == [tmp_path / "video.webm", tmp_path / "video-1.webm"]

    asyncio.run(run())


def test_backend_close_cleans_up_after_context_dispose_failure() -> None:
    async def run() -> None:
        backend = BrowserBackend(_config(), [])
        fake_context = RaisingDisposeContext()
        fake_browser = FakeClosable()
        fake_extension_relay = FakeClosable()
        fake_playwright = FakeClosable()
        backend._context = cast(Any, fake_context)
        backend._browser = cast(Any, fake_browser)
        backend._extension_relay = cast(Any, fake_extension_relay)
        backend._playwright = cast(Any, fake_playwright)

        await backend.close()

        assert fake_context.dispose_called is True
        assert fake_browser.closed is True
        assert fake_extension_relay.closed is True
        assert fake_playwright.closed is True
        assert backend._context is None
        assert backend._browser is None
        assert backend._extension_relay is None
        assert backend._playwright is None

    asyncio.run(run())


class ErrorBackend(BrowserBackend):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.closed = False

    async def _ensure_context(self, *, cwd: Path, roots: list[str] | None) -> Context:
        return cast(Context, FakeContext())

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeBrowserType()


class FakeBrowserType:
    def __init__(self) -> None:
        self.launch_called = False
        self.launch_options: dict[str, Any] | None = None
        self.persistent_user_data_dir: Path | None = None
        self.persistent_options: dict[str, Any] = {}

    async def launch(self, **options: Any) -> object:
        self.launch_called = True
        self.launch_options = options
        return object()

    async def launch_persistent_context(self, user_data_dir: Path, **options: Any) -> FakePersistentContext:
        self.persistent_user_data_dir = user_data_dir
        self.persistent_options = options
        return FakePersistentContext()


class FakePersistentContext:
    browser = object()


class FakeBrowserContext:
    def __init__(self, pages: list[FakePage]) -> None:
        self.pages = pages
        self._page_listeners: list[Callable[[FakePage], None]] = []

    async def add_init_script(self, *, path: Path) -> None:
        pass

    async def route(self, *args: Any) -> None:
        pass

    def on(self, event: str, callback: Any) -> None:
        if event == "page":
            self._page_listeners.append(callback)

    async def new_page(self) -> FakePage:
        page = FakePage("new")
        self.pages.append(page)
        self.emit_page(page)
        return page

    def emit_page(self, page: FakePage) -> None:
        for callback in self._page_listeners:
            callback(page)


class FakePage:
    def __init__(self, name: str) -> None:
        self.name = name
        self.listeners: dict[str, list[Any]] = {}
        self.screencast = FakeScreencast()

    def on(self, event: str, callback: Any) -> None:
        self.listeners.setdefault(event, []).append(callback)

    async def bring_to_front(self) -> None:
        pass


class FakeScreencast:
    def __init__(self) -> None:
        self.started: list[tuple[Path, dict[str, Any] | None]] = []
        self.stopped = 0

    async def start(self, *, path: Path, size: dict[str, Any] | None = None) -> None:
        self.started.append((path, size))

    async def stop(self) -> None:
        self.stopped += 1


class RaisingDisposeContext:
    def __init__(self) -> None:
        self.dispose_called = False

    def browser_context(self) -> None:
        return None

    async def dispose(self) -> None:
        self.dispose_called = True
        raise RuntimeError("dispose failed")


class FakeClosable:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True

    async def stop(self) -> None:
        self.closed = True


class FakeContext:
    cwd = Path.cwd()
    config = type(
        "FakeConfig",
        (),
        {
            "codegen": "python",
            "snapshot_mode": "none",
            "image_responses": "omit",
            "output_max_size": None,
            "output_mode": "stdout",
        },
    )()

    def current_tab(self) -> None:
        return None

    def tabs(self) -> list[object]:
        return []

    def configure_client(self, *, roots: list[Path] | None = None, cwd: Path | None = None) -> None:
        if cwd is not None:
            self.cwd = cwd

    def set_running_tool(self, name: str | None) -> None:
        pass

    def drain_unhandled_errors(self) -> list[str]:
        return []

    def redact_secrets(self, text: str) -> str:
        return text
