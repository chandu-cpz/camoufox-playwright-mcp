from __future__ import annotations

from typing import Any, Literal, cast
from urllib.parse import urlparse

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param

SameSite = Literal["Strict", "Lax", "None"]


async def _handle_cookie_list(context: Context, params: dict[str, Any], response: Response) -> None:
    cookies = await context.browser_context().cookies()
    if params.get("domain"):
        cookies = [cookie for cookie in cookies if params["domain"] in cookie["domain"]]
    if params.get("path"):
        cookies = [cookie for cookie in cookies if cookie["path"].startswith(params["path"])]
    response.add_text_result(
        "No cookies found"
        if not cookies
        else "\n".join(f'{c["name"]}={c["value"]} (domain: {c["domain"]}, path: {c["path"]})' for c in cookies)
    )
    response.add_code("await page.context.cookies()")


async def _handle_cookie_get(context: Context, params: dict[str, Any], response: Response) -> None:
    cookies = await context.browser_context().cookies()
    cookie = next((cookie for cookie in cookies if cookie["name"] == params["name"]), None)
    if cookie is None:
        response.add_text_result(f"Cookie '{params['name']}' not found")
    else:
        response.add_text_result(
            f'{cookie["name"]}={cookie["value"]} (domain: {cookie["domain"]}, path: {cookie["path"]}, '
            f'httpOnly: {str(cookie["httpOnly"]).lower()}, secure: {str(cookie["secure"]).lower()}, '
            f'sameSite: {cookie["sameSite"]})'
        )
    response.add_code("await page.context.cookies()")


async def _handle_cookie_set(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    parsed = urlparse(tab.page.url)
    cookie: dict[str, Any] = {
        "name": params["name"],
        "value": params["value"],
        "domain": params.get("domain") or parsed.hostname or "localhost",
        "path": params.get("path") or "/",
    }
    for key in ("expires", "httpOnly", "secure", "sameSite"):
        if params.get(key) is not None:
            cookie[key] = params[key]
    await context.browser_context().add_cookies(cast(Any, [cookie]))
    response.add_code(f"await page.context.add_cookies([{python_literal(cookie)}])")


async def _handle_cookie_delete(context: Context, params: dict[str, Any], response: Response) -> None:
    await context.browser_context().clear_cookies(name=params["name"])
    response.add_code(f"await page.context.clear_cookies(name={python_literal(params['name'])})")


async def _handle_cookie_clear(context: Context, _params: dict[str, Any], response: Response) -> None:
    await context.browser_context().clear_cookies()
    response.add_code("await page.context.clear_cookies()")


cookie_tools = [
    Tool(
        "browser_cookie_list",
        "storage",
        _handle_cookie_list,
        (param("domain", str | None, None), param("path", str | None, None)),
        tool_type="readOnly",
    ),
    Tool("browser_cookie_get", "storage", _handle_cookie_get, (param("name", str),), tool_type="readOnly"),
    Tool(
        "browser_cookie_set",
        "storage",
        _handle_cookie_set,
        (
            param("name", str),
            param("value", str),
            param("domain", str | None, None),
            param("path", str | None, None),
            param("expires", int | None, None),
            param("httpOnly", bool | None, None),
            param("secure", bool | None, None),
            param("sameSite", SameSite | None, None),
        ),
    ),
    Tool("browser_cookie_delete", "storage", _handle_cookie_delete, (param("name", str),)),
    Tool("browser_cookie_clear", "storage", _handle_cookie_clear),
]
