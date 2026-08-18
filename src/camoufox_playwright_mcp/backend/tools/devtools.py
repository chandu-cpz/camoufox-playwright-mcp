from __future__ import annotations

import asyncio
from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param, tab_tool


async def _handle_resume(context: Context, params: dict[str, Any], _response: Response) -> None:
    browser_context = context.browser_context()
    debugger = getattr(browser_context, "debugger", None)
    if debugger is None:
        raise ValueError(
            "browser_resume requires Playwright Python debugger support. "
            "Install a Playwright version that exposes browser_context.debugger."
        )

    paused = asyncio.Event()

    def listener(*_args: Any) -> None:
        paused_details_api = getattr(debugger, "paused_details", None)
        paused_details = paused_details_api() if callable(paused_details_api) else paused_details_api
        if paused_details:
            _remove_listener(debugger, "pausedstatechanged", listener)
            paused.set()

    def close_listener(*_args: Any) -> None:
        _remove_listener(debugger, "pausedstatechanged", listener)
        paused.set()

    debugger.on("pausedstatechanged", listener)
    browser_context.once("close", close_listener)
    try:
        if params.get("location"):
            file, line = _parse_location(params["location"])
            if line is None:
                await debugger.run_to({"file": file})
            else:
                await debugger.run_to({"file": file, "line": line})
        elif params.get("step"):
            await debugger.next()
        else:
            await debugger.resume()
        await paused.wait()
    finally:
        _remove_listener(debugger, "pausedstatechanged", listener)


async def _handle_highlight(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    resolved = await tab.resolve_target(target=params["target"], element=params.get("element"))
    # Python Playwright's Locator.highlight() takes no style kwarg and only
    # flashes a transient default outline. Accept the style param for tool-schema
    # compatibility but highlight plainly.
    await resolved.locator.highlight()
    response.add_text_result(f"Highlighted {params.get('element') or resolved.code}")


async def _handle_hide_highlight(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    target = params.get("target")
    # Python Playwright has no API to remove a highlight: Locator.highlight()
    # renders a transient outline that disappears on its own, so there is nothing
    # to hide. Resolve the target anyway so stale refs are still surfaced.
    if target:
        resolved = await tab.resolve_target(target=target, element=params.get("element"))
        response.add_text_result(f"Hid highlight for {params.get('element') or resolved.code}")
    else:
        response.add_text_result("Hid page highlight")


def _parse_location(value: str) -> tuple[str, int | None]:
    if ":" not in value:
        return value, None
    file, line_text = value.rsplit(":", 1)
    try:
        return file, int(line_text)
    except ValueError as exc:
        raise ValueError(f'Invalid location "{value}", expected format is <file>:<line>, e.g. "example.spec.ts:42"') from exc


def _remove_listener(emitter: Any, event: str, listener: Any) -> None:
    for method_name in ("off", "remove_listener", "removeListener"):
        method = getattr(emitter, method_name, None)
        if method is not None:
            method(event, listener)
            return


devtools_tools = [
    Tool(
        name="browser_resume",
        capability="devtools",
        parameters=(param("step", bool | None, None), param("location", str | None, None)),
        handler=_handle_resume,
    ),
    tab_tool(
        name="browser_highlight",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("target", str), param("element", str | None, None), param("style", str | None, None)),
        handler=_handle_highlight,
    ),
    tab_tool(
        name="browser_hide_highlight",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("target", str | None, None), param("element", str | None, None)),
        handler=_handle_hide_highlight,
    ),
]
