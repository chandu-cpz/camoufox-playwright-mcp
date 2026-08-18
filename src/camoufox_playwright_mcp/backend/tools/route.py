from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context, RouteEntry
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param


async def _handle_route(context: Context, params: dict[str, Any], response: Response) -> None:
    add_headers = _parse_headers(params.get("headers"))
    remove_headers = [header.strip() for header in params["removeHeaders"].split(",")] if params.get("removeHeaders") else None

    async def handler(route) -> None:
        if params.get("body") is not None or params.get("status") is not None:
            await route.fulfill(
                status=params.get("status") or 200,
                content_type=params.get("contentType"),
                body=params.get("body"),
            )
            return

        headers = dict(route.request.headers)
        for key, value in (add_headers or {}).items():
            headers[key] = value
        for header in remove_headers or []:
            headers.pop(header.lower(), None)
        await route.continue_(headers=headers)

    entry = RouteEntry(
        pattern=params["pattern"],
        status=params.get("status"),
        body=params.get("body"),
        content_type=params.get("contentType"),
        add_headers=add_headers,
        remove_headers=remove_headers,
        handler=handler,
    )
    await context.add_route(entry)
    response.add_text_result(f"Route added for pattern: {params['pattern']}")
    response.add_code(f"await page.context.route({python_literal(params['pattern'])}, route_handler)")


async def _handle_route_list(context: Context, _params: dict[str, Any], response: Response) -> None:
    routes = context.routes()
    if not routes:
        response.add_text_result("No active routes")
        return
    lines: list[str] = []
    for index, route in enumerate(routes, start=1):
        details: list[str] = []
        if route.status is not None:
            details.append(f"status={route.status}")
        if route.body is not None:
            details.append(f"body={route.body[:50] + '...' if len(route.body) > 50 else route.body}")
        if route.content_type:
            details.append(f"contentType={route.content_type}")
        if route.add_headers:
            details.append(f"addHeaders={python_literal(route.add_headers)}")
        if route.remove_headers:
            details.append(f"removeHeaders={','.join(route.remove_headers)}")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"{index}. {route.pattern}{suffix}")
    response.add_text_result("\n".join(lines))


async def _handle_unroute(context: Context, params: dict[str, Any], response: Response) -> None:
    removed = await context.remove_route(params.get("pattern"))
    if params.get("pattern"):
        response.add_text_result(f"Removed {removed} route(s) for pattern: {params['pattern']}")
    else:
        response.add_text_result(f"Removed all {removed} route(s)")


def _parse_headers(headers: list[str] | None) -> dict[str, str] | None:
    if not headers:
        return None
    parsed: dict[str, str] = {}
    for header in headers:
        name, _, value = header.partition(":")
        parsed[name.strip()] = value.strip()
    return parsed


route_tools = [
    Tool(
        name="browser_route",
        capability="network",
        parameters=(
            param("pattern", str),
            param("status", int | None, None),
            param("body", str | None, None),
            param("contentType", str | None, None),
            param("headers", list[str] | None, None),
            param("removeHeaders", str | None, None),
        ),
        handler=_handle_route,
    ),
    Tool(name="browser_route_list", capability="network", tool_type="readOnly", handler=_handle_route_list),
    Tool(
        name="browser_unroute",
        capability="network",
        parameters=(param("pattern", str | None, None),),
        handler=_handle_unroute,
    ),
]
