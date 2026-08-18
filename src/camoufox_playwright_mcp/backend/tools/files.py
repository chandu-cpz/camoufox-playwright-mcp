from __future__ import annotations

import asyncio
from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_file_upload(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    modal_state = next((state for state in tab.modal_states() if state.get("type") == "fileChooser"), None)
    if modal_state is None:
        raise ValueError('The tool "browser_file_upload" can only be used when there is related modal state present.')

    paths = params.get("paths")
    file_names = None
    if paths:
        file_names = await asyncio.gather(*(response.resolve_client_filename(path) for path in paths))

    response.set_include_snapshot()
    response.add_code(f"await file_chooser.set_files({python_literal(paths)})")
    tab.clear_modal_state(modal_state)
    file_chooser = modal_state["fileChooser"]
    if paths is not None:
        await tab.wait_for_completion(lambda: file_chooser.set_files(file_names or []))


async def _handle_drop(context: Context, params: dict[str, Any], response: Response) -> None:
    if not params.get("paths") and not params.get("data"):
        raise ValueError('At least one of "paths" or "data" must be provided.')

    # Python Playwright exposes no API for dropping files or MIME data onto an
    # arbitrary element: Locator.drag_to() only drags one element onto another,
    # and set_input_files() only applies to <input type=file>. Surface this as a
    # clear error instead of calling a nonexistent method.
    raise ValueError(
        "browser_drop is not supported by Python Playwright. "
        "Use browser_drag for element-to-element drag and drop, "
        "or browser_file_upload for file inputs."
    )


file_tools = [
    tab_tool(
        name="browser_file_upload",
        capability="core",
        parameters=(param("paths", list[str] | None, None),),
        handler=_handle_file_upload,
        clears_modal_state="fileChooser",
    ),
    tab_tool(
        name="browser_drop",
        capability="core",
        parameters=(
            param("target", str),
            param("element", str | None, None),
            param("paths", list[str] | None, None),
            param("data", dict[str, str] | None, None),
        ),
        handler=_handle_drop,
    ),
]
