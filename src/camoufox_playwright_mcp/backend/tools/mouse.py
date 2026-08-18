from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tab import Button
from camoufox_playwright_mcp.backend.tool import param, tab_tool

Number = int | float


def _mouse_click_code(
    *,
    x: Number,
    y: Number,
    button: Button | None,
    click_count: int | None,
    delay: Number | None,
) -> str:
    options: list[str] = []
    if button is not None:
        options.append(f"button={python_literal(button)}")
    if click_count is not None:
        options.append(f"click_count={python_literal(click_count)}")
    if delay is not None:
        options.append(f"delay={python_literal(delay)}")
    args = [python_literal(x), python_literal(y), *options]
    return f"await page.mouse.click({', '.join(args)})"


async def _handle_mouse_move_xy(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    x = params["x"]
    y = params["y"]
    response.add_code(f"# Move mouse to ({x}, {y})")
    response.add_code(f"await page.mouse.move({python_literal(x)}, {python_literal(y)})")
    await tab.mouse_move_xy(x=x, y=y)


async def _handle_mouse_click_xy(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    x = params["x"]
    y = params["y"]
    button = params.get("button")
    click_count = params.get("clickCount")
    delay = params.get("delay")
    response.set_include_snapshot()
    response.add_code(f"# Click mouse at coordinates ({x}, {y})")
    response.add_code(_mouse_click_code(x=x, y=y, button=button, click_count=click_count, delay=delay))
    await tab.mouse_click_xy(x=x, y=y, button=button, click_count=click_count, delay=delay)


async def _handle_mouse_down(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    button = params.get("button")
    response.add_code("# Press mouse down")
    if button is None:
        response.add_code("await page.mouse.down()")
    else:
        response.add_code(f"await page.mouse.down(button={python_literal(button)})")
    await tab.mouse_down(button=button)


async def _handle_mouse_up(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    button = params.get("button")
    response.add_code("# Press mouse up")
    if button is None:
        response.add_code("await page.mouse.up()")
    else:
        response.add_code(f"await page.mouse.up(button={python_literal(button)})")
    await tab.mouse_up(button=button)


async def _handle_mouse_wheel(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    delta_x = params.get("deltaX", 0)
    delta_y = params.get("deltaY", 0)
    response.add_code("# Scroll mouse wheel")
    response.add_code(f"await page.mouse.wheel({python_literal(delta_x)}, {python_literal(delta_y)})")
    await tab.mouse_wheel(delta_x=delta_x, delta_y=delta_y)


async def _handle_mouse_drag_xy(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    start_x = params["startX"]
    start_y = params["startY"]
    end_x = params["endX"]
    end_y = params["endY"]
    response.set_include_snapshot()
    response.add_code(f"# Drag mouse from ({start_x}, {start_y}) to ({end_x}, {end_y})")
    response.add_code(f"await page.mouse.move({python_literal(start_x)}, {python_literal(start_y)})")
    response.add_code("await page.mouse.down()")
    response.add_code(f"await page.mouse.move({python_literal(end_x)}, {python_literal(end_y)})")
    response.add_code("await page.mouse.up()")
    await tab.mouse_drag_xy(start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y)


mouse_tools = [
    tab_tool(
        name="browser_mouse_move_xy",
        capability="vision",
        tool_type="input",
        parameters=(param("x", Number), param("y", Number)),
        handler=_handle_mouse_move_xy,
    ),
    tab_tool(
        name="browser_mouse_click_xy",
        capability="vision",
        tool_type="input",
        parameters=(
            param("x", Number),
            param("y", Number),
            param("button", Button | None, None),
            param("clickCount", int | None, None),
            param("delay", Number | None, None),
        ),
        handler=_handle_mouse_click_xy,
    ),
    tab_tool(
        name="browser_mouse_down",
        capability="vision",
        tool_type="input",
        parameters=(param("button", Button | None, None),),
        handler=_handle_mouse_down,
    ),
    tab_tool(
        name="browser_mouse_up",
        capability="vision",
        tool_type="input",
        parameters=(param("button", Button | None, None),),
        handler=_handle_mouse_up,
    ),
    tab_tool(
        name="browser_mouse_wheel",
        capability="vision",
        tool_type="input",
        parameters=(param("deltaX", Number, 0), param("deltaY", Number, 0)),
        handler=_handle_mouse_wheel,
    ),
    tab_tool(
        name="browser_mouse_drag_xy",
        capability="vision",
        tool_type="input",
        parameters=(
            param("startX", Number),
            param("startY", Number),
            param("endX", Number),
            param("endY", Number),
        ),
        handler=_handle_mouse_drag_xy,
    ),
]
