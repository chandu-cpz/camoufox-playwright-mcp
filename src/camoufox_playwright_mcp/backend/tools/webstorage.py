from __future__ import annotations

from typing import Any, Literal

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool

StorageKind = Literal["localStorage", "sessionStorage"]


async def _storage(tab, kind: StorageKind):
    return tab.page.local_storage if kind == "localStorage" else tab.page.session_storage


def _storage_code(kind: StorageKind) -> str:
    return "local_storage" if kind == "localStorage" else "session_storage"


def _not_found(kind: StorageKind, key: str) -> str:
    return f"{kind} key '{key}' not found"


async def _handle_list(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    storage = await _storage(tab, kind)
    items = await storage.items()
    response.add_text_result(
        f"No {kind} items found" if not items else "\n".join(f"{item['name']}={item['value']}" for item in items)
    )
    response.add_code(f"await page.{_storage_code(kind)}.items()")


async def _handle_get(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    key = params["key"]
    value = await (await _storage(tab, kind)).get_item(key)
    response.add_text_result(_not_found(kind, key) if value is None else f"{key}={value}")
    response.add_code(f"await page.{_storage_code(kind)}.get_item({python_literal(key)})")


async def _handle_set(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    await (await _storage(tab, kind)).set_item(params["key"], params["value"])
    response.add_code(
        f"await page.{_storage_code(kind)}.set_item({python_literal(params['key'])}, {python_literal(params['value'])})"
    )


async def _handle_delete(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    await (await _storage(tab, kind)).remove_item(params["key"])
    response.add_code(f"await page.{_storage_code(kind)}.remove_item({python_literal(params['key'])})")


async def _handle_clear(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    await (await _storage(tab, kind)).clear()
    response.add_code(f"await page.{_storage_code(kind)}.clear()")


def _with_kind(handler, kind: StorageKind):
    async def wrapped(context: Context, params: dict[str, Any], response: Response) -> None:
        await handler(context, {**params, "_kind": kind}, response)

    return wrapped


webstorage_tools = [
    tab_tool("browser_localstorage_list", "storage", _with_kind(_handle_list, "localStorage"), tool_type="readOnly"),
    tab_tool(
        "browser_localstorage_get",
        "storage",
        _with_kind(_handle_get, "localStorage"),
        (param("key", str),),
        tool_type="readOnly",
    ),
    tab_tool(
        "browser_localstorage_set",
        "storage",
        _with_kind(_handle_set, "localStorage"),
        (param("key", str), param("value", str)),
    ),
    tab_tool("browser_localstorage_delete", "storage", _with_kind(_handle_delete, "localStorage"), (param("key", str),)),
    tab_tool("browser_localstorage_clear", "storage", _with_kind(_handle_clear, "localStorage")),
    tab_tool("browser_sessionstorage_list", "storage", _with_kind(_handle_list, "sessionStorage"), tool_type="readOnly"),
    tab_tool(
        "browser_sessionstorage_get",
        "storage",
        _with_kind(_handle_get, "sessionStorage"),
        (param("key", str),),
        tool_type="readOnly",
    ),
    tab_tool(
        "browser_sessionstorage_set",
        "storage",
        _with_kind(_handle_set, "sessionStorage"),
        (param("key", str), param("value", str)),
    ),
    tab_tool("browser_sessionstorage_delete", "storage", _with_kind(_handle_delete, "sessionStorage"), (param("key", str),)),
    tab_tool("browser_sessionstorage_clear", "storage", _with_kind(_handle_clear, "sessionStorage")),
]
