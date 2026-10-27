from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anyio
import pytest

from camoufox_playwright_mcp.mcp.server import PlaywrightMCPServer, _session_task_group


def test_session_task_group_ends_with_the_session() -> None:
    """The session's own task group is cancelled on close; FastMCP's is not."""

    session_lifetime = object()
    fastmcp_subscription = object()

    both = SimpleNamespace(_task_group=session_lifetime, _subscription_task_group=fastmcp_subscription)
    assert _session_task_group(cast(Any, both)) is session_lifetime

    fallback_only = SimpleNamespace(_task_group=None, _subscription_task_group=fastmcp_subscription)
    assert _session_task_group(cast(Any, fallback_only)) is fastmcp_subscription

    assert _session_task_group(cast(Any, SimpleNamespace())) is None


def test_watchdog_survives_unsupported_signal_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows has no loop.add_signal_handler(), so anyio raises NotImplementedError.

    The server must keep serving (shutdown then happens on stdin EOF / client
    disconnect) instead of dying at startup, and it must still close backends.
    """

    class FakeApp:
        ran = False

        async def run_async(self, **kwargs: Any) -> None:
            self.ran = True
            await anyio.sleep(0)

    class FakePool:
        closed = False

        async def close_all(self) -> None:
            self.closed = True

    app = FakeApp()
    pool = FakePool()

    def unsupported(*args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("add_signal_handler is not supported on this platform")

    monkeypatch.setattr("camoufox_playwright_mcp.mcp.server.anyio.open_signal_receiver", unsupported)

    server = PlaywrightMCPServer(
        app=cast(Any, app),
        config=cast(Any, SimpleNamespace(server_port=None)),
        backend_pool=cast(Any, pool),
    )

    anyio.run(server._run_with_watchdog, "stdio")

    assert app.ran is True
    assert pool.closed is True
