from __future__ import annotations

import json
from typing import Any

from camoufox_playwright_mcp.backend.context import Context, FilenameTemplate
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param


async def _handle_storage_state(context: Context, params: dict[str, Any], response: Response) -> None:
    state = await context.browser_context().storage_state()
    serialized = json.dumps(state, indent=2)
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(prefix="storage-state", ext="json", suggested_filename=params.get("filename")),
        "Storage state",
    )
    response.add_code(f"await page.context.storage_state(path={resolved_file.relative_name!r})")
    await response.add_file_result(resolved_file, serialized)


async def _handle_set_storage_state(context: Context, params: dict[str, Any], response: Response) -> None:
    resolved_filename = await response.resolve_client_filename(params["filename"])
    await context.browser_context().set_storage_state(resolved_filename)
    response.add_text_result(f"Storage state restored from {params['filename']}")
    response.add_code(f"await page.context.set_storage_state({params['filename']!r})")


storage_tools = [
    Tool(
        name="browser_storage_state",
        capability="storage",
        tool_type="readOnly",
        parameters=(param("filename", str | None, None),),
        handler=_handle_storage_state,
    ),
    Tool(
        name="browser_set_storage_state",
        capability="storage",
        parameters=(param("filename", str),),
        handler=_handle_set_storage_state,
    ),
]
