from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_dialog(context: Context, params: dict[str, Any], _response: Response) -> None:
    tab = await context.ensure_tab()
    dialog_state = next((state for state in tab.modal_states() if state.get("type") == "dialog"), None)
    if dialog_state is None:
        raise ValueError("No dialog visible")
    tab.clear_modal_state(dialog_state)
    dialog = dialog_state["dialog"]
    if params["accept"]:
        await tab.wait_for_completion(lambda: dialog.accept(params.get("promptText")))
    else:
        await tab.wait_for_completion(dialog.dismiss)


dialog_tools = [
    tab_tool(
        name="browser_handle_dialog",
        capability="core",
        parameters=(
            param("accept", bool),
            param("promptText", str | None, None),
        ),
        handler=_handle_dialog,
        clears_modal_state="dialog",
    ),
]
