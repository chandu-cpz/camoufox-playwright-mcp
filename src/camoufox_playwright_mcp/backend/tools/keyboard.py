from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_call, python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_press_key(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    key = params["key"]
    response.add_code(f"# Press {key}")
    response.add_code(f"await page.keyboard.press({python_literal(key)})")
    if key == "Enter":
        response.set_include_snapshot()
    await tab.press_key(key)


async def _handle_type(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    secret = context.lookup_secret(params["text"])
    submit = params.get("submit", False)
    slowly = params.get("slowly", False)
    if slowly:
        response.set_include_snapshot()
        response.add_code(f"await page.{resolved.code}.press_sequentially({secret.code})")
    else:
        response.add_code(f"await page.{resolved.code}.fill({secret.code})")
    if submit:
        response.set_include_snapshot()
        response.add_code(python_call(resolved.code, "press", "Enter"))
    await tab.type_text(resolved, text=secret.value, submit=submit, slowly=slowly)


async def _handle_press_sequentially(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    text = params["text"]
    response.add_code(f"# Press {text}")
    response.add_code(f"await page.keyboard.type({python_literal(text)})")
    if params.get("submit"):
        response.set_include_snapshot()
        response.add_code("await page.keyboard.press(\"Enter\")")
    await tab.press_sequentially(text=text, submit=params.get("submit", False))


async def _handle_keydown(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    key = params["key"]
    response.add_code(f"await page.keyboard.down({python_literal(key)})")
    await tab.key_down(key)


async def _handle_keyup(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    key = params["key"]
    response.add_code(f"await page.keyboard.up({python_literal(key)})")
    await tab.key_up(key)


keyboard_tools = [
    tab_tool(
        name="browser_press_key",
        capability="core-input",
        tool_type="input",
        parameters=(param("key", str),),
        handler=_handle_press_key,
    ),
    tab_tool(
        name="browser_type",
        capability="core-input",
        tool_type="input",
        parameters=(
            param("target", str),
            param("text", str),
            param("element", str | None, None),
            param("submit", bool, False),
            param("slowly", bool, False),
        ),
        handler=_handle_type,
    ),
    tab_tool(
        name="browser_press_sequentially",
        capability="core-input",
        tool_type="input",
        parameters=(param("text", str), param("submit", bool, False)),
        handler=_handle_press_sequentially,
        skill_only=True,
    ),
    tab_tool(
        name="browser_keydown",
        capability="core-input",
        tool_type="input",
        parameters=(param("key", str),),
        handler=_handle_keydown,
        skill_only=True,
    ),
    tab_tool(
        name="browser_keyup",
        capability="core-input",
        tool_type="input",
        parameters=(param("key", str),),
        handler=_handle_keyup,
        skill_only=True,
    ),
]
