from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_console_messages(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    level = params.get("level", "info")
    count = await tab.console_message_count()
    header = [f"Total messages: {count['total']} (Errors: {count['errors']}, Warnings: {count['warnings']})"]
    messages = await tab.console_messages(level=level, all_messages=params.get("all", False))
    if len(messages) != count["total"]:
        header.append(f'Returning {len(messages)} messages for level "{level}"')
    text = "\n".join([*header, "", *messages])
    await response.add_result(
        "Console",
        text,
        prefix="console",
        ext="log",
        suggested_filename=params.get("filename"),
    )


async def _handle_console_clear(context: Context, _params: dict[str, Any], _response: Response) -> None:
    tab = await context.ensure_tab()
    await tab.clear_console_messages()


console_tools = [
    tab_tool(
        name="browser_console_messages",
        capability="core",
        tool_type="readOnly",
        parameters=(
            param("level", str, "info"),
            param("all", bool, False),
            param("filename", str | None, None),
        ),
        handler=_handle_console_messages,
    ),
    tab_tool(
        name="browser_console_clear",
        capability="core",
        tool_type="readOnly",
        handler=_handle_console_clear,
        skill_only=True,
    ),
]
