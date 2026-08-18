from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_dict
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param, tab_tool


async def _handle_resize(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    width = params["width"]
    height = params["height"]
    await tab.resize(width=width, height=height)
    response.add_code(f"await page.set_viewport_size({python_dict([('width', width), ('height', height)])})")


async def _handle_close(_context: Context, _params: dict[str, Any], response: Response) -> None:
    response.add_text_result("No open tabs. Navigate to a URL to create one.")
    response.add_code("await page.close()")
    response.set_close()


common_tools = [
    tab_tool(
        name="browser_resize",
        capability="core",
        parameters=(param("width", int), param("height", int)),
        handler=_handle_resize,
    ),
    Tool(
        name="browser_close",
        capability="core",
        handler=_handle_close,
    ),
]
