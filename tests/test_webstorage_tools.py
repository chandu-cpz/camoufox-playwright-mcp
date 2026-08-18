from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tools.webstorage import webstorage_tools
from camoufox_playwright_mcp.mcp.config import resolve_config


class FakePageWithEvaluate:
    def __init__(self) -> None:
        self._local_storage: dict[str, str] = {}
        self._session_storage: dict[str, str] = {}

    async def evaluate(self, script: str, arg: Any = None) -> Any:
        storage = self._local_storage if "localStorage" in script else self._session_storage
        if "out.push" in script or "items.push" in script:
            return [{"name": k, "value": v} for k, v in storage.items()]
        if "getItem" in script:
            key = arg if isinstance(arg, str) else (arg[0] if isinstance(arg, list) and arg else None)
            return storage.get(str(key)) if key is not None else None
        if "setItem" in script:
            k, v = arg
            storage[str(k)] = str(v)
            return None
        if "removeItem" in script:
            storage.pop(str(arg), None)
            return None
        if "clear" in script:
            storage.clear()
            return None
        raise NotImplementedError(f"Script not mocked: {script}")


class FakeTab:
    def __init__(self) -> None:
        self.page = FakePageWithEvaluate()


class FakeContext:
    def __init__(self) -> None:
        self._tab = FakeTab()
        self.config = resolve_config()
        self.cwd = Path.cwd()

    async def ensure_tab(self) -> FakeTab:
        return self._tab


@pytest.mark.anyio
async def test_localstorage_crud_flow() -> None:
    tools_by_name = {t.name: t for t in webstorage_tools}
    context = cast(Context, FakeContext())

    # 1. List initially empty
    resp = Response(context, tool_name="browser_localstorage_list", tool_args={})
    await tools_by_name["browser_localstorage_list"].handler(context, {}, resp)
    assert any("No localStorage items found" in r for r in resp._results)

    # 2. Set item
    resp = Response(context, tool_name="browser_localstorage_set", tool_args={"key": "user", "value": "alice"})
    await tools_by_name["browser_localstorage_set"].handler(context, {"key": "user", "value": "alice"}, resp)
    tab = await context.ensure_tab()
    assert cast(FakePageWithEvaluate, tab.page)._local_storage["user"] == "alice"

    # 3. Get item
    resp = Response(context, tool_name="browser_localstorage_get", tool_args={"key": "user"})
    await tools_by_name["browser_localstorage_get"].handler(context, {"key": "user"}, resp)
    assert any("user=alice" in r for r in resp._results)

    # 4. List contains item
    resp = Response(context, tool_name="browser_localstorage_list", tool_args={})
    await tools_by_name["browser_localstorage_list"].handler(context, {}, resp)
    assert any("user=alice" in r for r in resp._results)

    # 5. Delete item
    resp = Response(context, tool_name="browser_localstorage_delete", tool_args={"key": "user"})
    await tools_by_name["browser_localstorage_delete"].handler(context, {"key": "user"}, resp)
    assert "user" not in cast(FakePageWithEvaluate, tab.page)._local_storage

    # 6. Clear storage
    cast(FakePageWithEvaluate, tab.page)._local_storage["k1"] = "v1"
    cast(FakePageWithEvaluate, tab.page)._local_storage["k2"] = "v2"
    resp = Response(context, tool_name="browser_localstorage_clear", tool_args={})
    await tools_by_name["browser_localstorage_clear"].handler(context, {}, resp)
    assert len(cast(FakePageWithEvaluate, tab.page)._local_storage) == 0


@pytest.mark.anyio
async def test_sessionstorage_crud_flow() -> None:
    tools_by_name = {t.name: t for t in webstorage_tools}
    context = cast(Context, FakeContext())

    # 1. Set item
    resp = Response(context, tool_name="browser_sessionstorage_set", tool_args={"key": "session_id", "value": "12345"})
    await tools_by_name["browser_sessionstorage_set"].handler(context, {"key": "session_id", "value": "12345"}, resp)
    tab = await context.ensure_tab()
    assert cast(FakePageWithEvaluate, tab.page)._session_storage["session_id"] == "12345"

    # 2. Get item
    resp = Response(context, tool_name="browser_sessionstorage_get", tool_args={"key": "session_id"})
    await tools_by_name["browser_sessionstorage_get"].handler(context, {"key": "session_id"}, resp)
    assert any("session_id=12345" in r for r in resp._results)

    # 3. List
    resp = Response(context, tool_name="browser_sessionstorage_list", tool_args={})
    await tools_by_name["browser_sessionstorage_list"].handler(context, {}, resp)
    assert any("session_id=12345" in r for r in resp._results)

    # 4. Delete item
    resp = Response(context, tool_name="browser_sessionstorage_delete", tool_args={"key": "session_id"})
    await tools_by_name["browser_sessionstorage_delete"].handler(context, {"key": "session_id"}, resp)
    assert "session_id" not in cast(FakePageWithEvaluate, tab.page)._session_storage
