from __future__ import annotations

from typing import Any, Literal

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool

StorageKind = Literal["localStorage", "sessionStorage"]


class WebStorage:
    def __init__(self, page: Any, kind: StorageKind):
        self._page = page
        self._kind = kind

    async def items(self) -> list[dict[str, str]]:
        attr_name = "local_storage" if self._kind == "localStorage" else "session_storage"
        native = getattr(self._page, attr_name, None)
        if native is not None and hasattr(native, "items"):
            return await native.items()
        return await self._page.evaluate(
            f"""() => {{
                const s = window.{self._kind};
                const out = [];
                for (let i = 0; i < s.length; i++) {{
                    const k = s.key(i);
                    out.push({{ name: k, value: s.getItem(k) }});
                }}
                return out;
            }}"""
        )

    async def get_item(self, key: str) -> str | None:
        attr_name = "local_storage" if self._kind == "localStorage" else "session_storage"
        native = getattr(self._page, attr_name, None)
        if native is not None and hasattr(native, "get_item"):
            return await native.get_item(key)
        return await self._page.evaluate(f"k => window.{self._kind}.getItem(k)", key)

    async def set_item(self, key: str, value: str) -> None:
        attr_name = "local_storage" if self._kind == "localStorage" else "session_storage"
        native = getattr(self._page, attr_name, None)
        if native is not None and hasattr(native, "set_item"):
            await native.set_item(key, value)
            return
        await self._page.evaluate(f"([k, v]) => window.{self._kind}.setItem(k, v)", [key, value])

    async def remove_item(self, key: str) -> None:
        attr_name = "local_storage" if self._kind == "localStorage" else "session_storage"
        native = getattr(self._page, attr_name, None)
        if native is not None and hasattr(native, "remove_item"):
            await native.remove_item(key)
            return
        await self._page.evaluate(f"k => window.{self._kind}.removeItem(k)", key)

    async def clear(self) -> None:
        attr_name = "local_storage" if self._kind == "localStorage" else "session_storage"
        native = getattr(self._page, attr_name, None)
        if native is not None and hasattr(native, "clear"):
            await native.clear()
            return
        await self._page.evaluate(f"() => window.{self._kind}.clear()")


def _storage(tab: Any, kind: StorageKind) -> WebStorage:
    return WebStorage(tab.page, kind)


def _storage_code(kind: StorageKind) -> str:
    return "local_storage" if kind == "localStorage" else "session_storage"


def _not_found(kind: StorageKind, key: str) -> str:
    return f"{kind} key '{key}' not found"


async def _handle_list(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    storage = _storage(tab, kind)
    items = await storage.items()
    response.add_text_result(
        f"No {kind} items found" if not items else "\n".join(f"{item['name']}={item['value']}" for item in items)
    )
    response.add_code(f"await page.{_storage_code(kind)}.items()")


async def _handle_get(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    key = params["key"]
    storage = _storage(tab, kind)
    value = await storage.get_item(key)
    response.add_text_result(_not_found(kind, key) if value is None else f"{key}={value}")
    response.add_code(f"await page.{_storage_code(kind)}.get_item({python_literal(key)})")


async def _handle_set(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    storage = _storage(tab, kind)
    await storage.set_item(params["key"], params["value"])
    response.add_code(
        f"await page.{_storage_code(kind)}.set_item({python_literal(params['key'])}, {python_literal(params['value'])})"
    )


async def _handle_delete(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    storage = _storage(tab, kind)
    await storage.remove_item(params["key"])
    response.add_code(f"await page.{_storage_code(kind)}.remove_item({python_literal(params['key'])})")


async def _handle_clear(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    kind: StorageKind = params["_kind"]
    storage = _storage(tab, kind)
    await storage.clear()
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
