from __future__ import annotations

import asyncio
from typing import Any

from camoufox_playwright_mcp.backend.tab import Tab


def _bare_tab(**attrs: Any) -> Tab:
    tab = object.__new__(Tab)
    for name, value in attrs.items():
        setattr(tab, name, value)
    return tab


class FakeProbePage:
    def __init__(self, *, hang: bool = False) -> None:
        self.hang = hang
        self.probes = 0

    async def evaluate(self, _expr: str) -> int:
        self.probes += 1
        if self.hang:
            await asyncio.sleep(30)
            raise AssertionError("unreachable")
        return 2


def _dialog_state(**overrides: Any) -> dict[str, Any]:
    state: dict[str, Any] = {
        "type": "dialog",
        "description": '["alert" dialog with message "Hello"]',
        "dialog": object(),
        "clearedBy": {"tool": "browser_handle_dialog"},
    }
    state.update(overrides)
    return state


def test_prune_stale_dialogs_clears_dead_dialog() -> None:
    async def run() -> None:
        page = FakeProbePage(hang=False)
        modal_event = asyncio.Event()
        modal_event.set()
        tab = _bare_tab(
            page=page,
            _modal_states=[_dialog_state()],
            _modal_event=modal_event,
        )

        await tab.prune_stale_dialogs()

        assert tab.modal_states() == []
        assert page.probes == 1
        assert not tab._modal_event.is_set()

    asyncio.run(run())


def test_prune_stale_dialogs_keeps_live_dialog() -> None:
    async def run() -> None:
        page = FakeProbePage(hang=True)
        modal_event = asyncio.Event()
        tab = _bare_tab(
            page=page,
            _modal_states=[_dialog_state()],
            _modal_event=modal_event,
        )

        await tab.prune_stale_dialogs()

        assert len(tab.modal_states()) == 1
        assert page.probes == 1

    asyncio.run(run())


def test_prune_stale_dialogs_keeps_file_chooser_and_skips_probe() -> None:
    async def run() -> None:
        page = FakeProbePage(hang=False)
        tab = _bare_tab(
            page=page,
            _modal_states=[
                {
                    "type": "fileChooser",
                    "description": "[file chooser]",
                    "clearedBy": {"tool": "browser_file_upload"},
                }
            ],
            _modal_event=asyncio.Event(),
        )

        await tab.prune_stale_dialogs()

        assert len(tab.modal_states()) == 1
        assert page.probes == 0

    asyncio.run(run())


def test_prune_stale_dialogs_skips_probe_when_no_dialogs() -> None:
    async def run() -> None:
        page = FakeProbePage(hang=False)
        tab = _bare_tab(page=page, _modal_states=[], _modal_event=asyncio.Event())

        await tab.prune_stale_dialogs()

        assert tab.modal_states() == []
        assert page.probes == 0

    asyncio.run(run())
