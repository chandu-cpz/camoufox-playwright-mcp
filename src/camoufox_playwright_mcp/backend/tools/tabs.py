from __future__ import annotations

from typing import Any, Literal

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response, render_tabs_markdown
from camoufox_playwright_mcp.backend.tool import Tool, param

TabAction = Literal["list", "new", "close", "select"]


async def _handle_tabs(context: Context, params: dict[str, Any], response: Response) -> None:
    action = params["action"]
    if action == "list":
        await context.ensure_tab()
    elif action == "new":
        tab = await context.new_tab()
        if params.get("url"):
            url = await tab.check_url_and_navigate(params["url"])
            response.set_include_snapshot()
            response.add_code(f"await page.goto({python_literal(url)})")
    elif action == "close":
        await context.close_tab(params.get("index"))
    elif action == "select":
        if params.get("index") is None:
            raise ValueError("Tab index is required")
        await context.select_tab(params["index"])

    headers = [await tab.header_snapshot() for tab in context.tabs()]
    response.add_text_result("\n".join(render_tabs_markdown(headers)))


tabs_tools = [
    Tool(
        name="browser_tabs",
        capability="core-tabs",
        parameters=(
            param("action", TabAction),
            param("index", int | None, None),
            param("url", str | None, None),
        ),
        handler=_handle_tabs,
    )
]
