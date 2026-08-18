from __future__ import annotations

import asyncio
from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param


async def _handle_wait_for(context: Context, params: dict[str, Any], response: Response) -> None:
    if not params.get("text") and not params.get("textGone") and not params.get("time"):
        raise ValueError("Either time, text or textGone must be provided")

    if params.get("time"):
        seconds = params["time"]
        response.add_code(f"await asyncio.sleep({python_literal(seconds)})")
        await asyncio.sleep(min(30, seconds))

    tab = context.current_tab_or_die()
    if params.get("textGone"):
        text_gone = params["textGone"]
        response.add_code(f"await page.get_by_text({python_literal(text_gone)}).first.wait_for(state=\"hidden\")")
        await tab.page.get_by_text(text_gone).first.wait_for(state="hidden", timeout=tab.action_timeout)

    if params.get("text"):
        text = params["text"]
        response.add_code(f"await page.get_by_text({python_literal(text)}).first.wait_for(state=\"visible\")")
        await tab.page.get_by_text(text).first.wait_for(state="visible", timeout=tab.action_timeout)

    response.add_text_result(f"Waited for {params.get('text') or params.get('textGone') or params.get('time')}")
    response.set_include_snapshot()


wait_tools = [
    Tool(
        name="browser_wait_for",
        capability="core",
        tool_type="assertion",
        parameters=(
            param("time", int | float | None, None),
            param("text", str | None, None),
            param("textGone", str | None, None),
        ),
        handler=_handle_wait_for,
    )
]
