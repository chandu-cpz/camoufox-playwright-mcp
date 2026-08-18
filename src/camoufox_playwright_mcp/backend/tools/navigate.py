from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param, tab_tool


async def _handle_navigate(context: Context, params: dict[str, Any], response: Response) -> None:
    resolved_url = await context.check_url_and_navigate(params["url"])
    response.set_include_snapshot()
    response.add_code(f"await page.goto({python_literal(resolved_url)})")


async def _handle_go_back(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    await tab.go_back()
    response.set_include_snapshot()
    response.add_code("await page.go_back()")


async def _handle_go_forward(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    await tab.go_forward()
    response.set_include_snapshot()
    response.add_code("await page.go_forward()")


async def _handle_reload(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    await tab.reload()
    response.set_include_snapshot()
    response.add_code("await page.reload()")


navigate_tools = [
    Tool(
        name="browser_navigate",
        capability="core-navigation",
        title="Navigate to a URL",
        description="Navigate to a URL",
        parameters=(param("url", str, description="The URL to navigate to"),),
        handler=_handle_navigate,
    ),
    tab_tool(
        name="browser_navigate_back",
        capability="core-navigation",
        title="Go back",
        description="Go back to the previous page in the history",
        handler=_handle_go_back,
    ),
    tab_tool(
        name="browser_navigate_forward",
        capability="core-navigation",
        title="Go forward",
        description="Go forward to the next page in the history",
        handler=_handle_go_forward,
        skill_only=True,
    ),
    tab_tool(
        name="browser_reload",
        capability="core-navigation",
        title="Reload the page",
        description="Reload the current page",
        handler=_handle_reload,
        skill_only=True,
    ),
]
