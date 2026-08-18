from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from camoufox_playwright_mcp.backend.tab import Tab


def _bare_tab(**attrs: Any) -> Tab:
    tab = object.__new__(Tab)
    for name, value in attrs.items():
        setattr(tab, name, value)
    return tab


class FakeContext:
    def track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        return task


class FakePage:
    def __init__(self) -> None:
        self.request_listener = None

    def on(self, event: str, listener: Any) -> None:
        assert event == "request"
        self.request_listener = listener

    def remove_listener(self, event: str, listener: Any) -> None:
        assert event == "request"
        self.request_listener = None


class BoomRequest:
    def is_navigation_request(self) -> bool:
        return False

    async def response(self) -> None:
        raise RuntimeError("watcher boom")


def _ready_tab(page: FakePage) -> Tab:
    async def noop() -> None:
        pass

    async def noop_timeout(_seconds: float) -> None:
        pass

    return _bare_tab(
        page=page,
        _initialized=noop(),
        _modal_states=[],
        _modal_event=asyncio.Event(),
        context=FakeContext(),
        wait_for_timeout=noop_timeout,
    )


def test_settle_watcher_failure_does_not_fail_completed_action(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def run() -> None:
        page = FakePage()
        tab = _ready_tab(page)

        async def action() -> str:
            assert page.request_listener is not None
            page.request_listener(BoomRequest())
            return "clicked"

        with caplog.at_level(
            logging.WARNING, logger="camoufox_playwright_mcp.backend.tab"
        ):
            result = await tab.wait_for_completion(action)

        assert result == "clicked"
        assert "Settle watcher failed after a completed action" in caplog.text

    asyncio.run(run())


def test_action_failure_still_propagates() -> None:
    async def run() -> None:
        tab = _ready_tab(FakePage())

        async def action() -> None:
            raise RuntimeError("action failed")

        with pytest.raises(RuntimeError, match="action failed"):
            await tab.wait_for_completion(action)

    asyncio.run(run())
