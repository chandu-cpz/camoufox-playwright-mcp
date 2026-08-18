from __future__ import annotations

import asyncio
from typing import Any, cast

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tools.devtools import _handle_resume


class FakeDebugger:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.paused_details: Any = None
        self._listeners: list[Any] = []

    def on(self, event: str, listener: Any) -> None:
        assert event == "pausedstatechanged"
        self._listeners.append(listener)

    def off(self, event: str, listener: Any) -> None:
        assert event == "pausedstatechanged"
        if listener in self._listeners:
            self._listeners.remove(listener)

    async def resume(self) -> None:
        self.calls.append(("resume", None))

    async def next(self) -> None:
        self.calls.append(("next", None))
        self._pause()

    async def run_to(self, location: dict[str, Any]) -> None:
        self.calls.append(("run_to", location))
        self._pause()

    def _pause(self) -> None:
        self.paused_details = {"location": {"file": "test.py", "line": 7}}
        for listener in list(self._listeners):
            listener()


class FakeBrowserContext:
    def __init__(self) -> None:
        self.debugger = FakeDebugger()
        self._close_listener: Any = None

    def once(self, event: str, listener: Any) -> None:
        assert event == "close"
        self._close_listener = listener

    def close_for_test(self) -> None:
        assert self._close_listener is not None
        self._close_listener()


class FakeContext:
    def __init__(self, browser_context: FakeBrowserContext) -> None:
        self._browser_context = browser_context

    def browser_context(self) -> FakeBrowserContext:
        return self._browser_context


def test_browser_resume_calls_resume_and_waits_for_close() -> None:
    browser_context = FakeBrowserContext()

    async def run() -> None:
        task = asyncio.create_task(
            _handle_resume(cast(Context, FakeContext(browser_context)), {}, cast(Response, None))
        )
        await asyncio.sleep(0)
        assert browser_context.debugger.calls == [("resume", None)]
        browser_context.close_for_test()
        await task

    asyncio.run(run())


def test_browser_resume_calls_next_and_waits_for_pause() -> None:
    browser_context = FakeBrowserContext()

    asyncio.run(_handle_resume(cast(Context, FakeContext(browser_context)), {"step": True}, cast(Response, None)))

    assert browser_context.debugger.calls == [("next", None)]


def test_browser_resume_calls_run_to_with_location() -> None:
    browser_context = FakeBrowserContext()

    asyncio.run(
        _handle_resume(cast(Context, FakeContext(browser_context)), {"location": "example.py:42"}, cast(Response, None))
    )

    assert browser_context.debugger.calls == [("run_to", {"file": "example.py", "line": 42})]
