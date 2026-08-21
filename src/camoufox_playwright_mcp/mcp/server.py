from __future__ import annotations

import os
import signal
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import wraps
from importlib.metadata import PackageNotFoundError, version
from inspect import Parameter, Signature, isawaitable
from typing import Any, Literal, cast
from urllib.parse import unquote, urlparse

import anyio
import mcp.types as mt
from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.server.context import Context as FastMCPContext
from fastmcp.server.middleware import CallNext, MiddlewareContext
from fastmcp.server.middleware import Middleware as FastMCPMiddleware
from fastmcp.tools.base import ToolResult
from mcp.types import ToolAnnotations
from playwright.async_api import BrowserContext as PlaywrightBrowserContext
from pydantic import ValidationError as PydanticValidationError
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from camoufox_playwright_mcp.backend import BrowserBackend
from camoufox_playwright_mcp.backend.tools import filtered_tools
from camoufox_playwright_mcp.mcp.config import ServerConfig, resolve_config


@dataclass(slots=True)
class PlaywrightMCPServer:
    app: FastMCP
    config: ServerConfig
    backend_pool: BackendPool
    _cancel_scope: anyio.CancelScope | None = field(default=None, init=False)

    @property
    def backend(self) -> BrowserBackend:
        return self.backend_pool.default_backend()

    def trigger_shutdown(self) -> None:
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

    def run(self) -> None:
        anyio.run(self.run_async)

    async def run_async(self) -> None:
        if self.config.server_port is None:
            await self._run_with_watchdog("stdio", show_banner=False, log_level="ERROR")
            return
        await self._run_with_watchdog(
            "http",
            host=self.config.server_host or "localhost",
            port=self.config.server_port,
            show_banner=False,
            log_level="ERROR",
            middleware=_http_middleware(self.config),
        )

    async def _run_with_watchdog(
        self,
        transport: Literal["stdio", "http", "sse", "streamable-http"],
        **transport_kwargs: Any,
    ) -> None:
        async def watch_signals(scope: anyio.CancelScope) -> None:
            with anyio.open_signal_receiver(signal.SIGINT, signal.SIGTERM) as signals:
                async for _signum in signals:
                    scope.cancel()
                    return

        with anyio.CancelScope() as scope:
            self._cancel_scope = scope
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(watch_signals, scope)
                try:
                    await self.app.run_async(transport=transport, **transport_kwargs)
                finally:
                    task_group.cancel_scope.cancel()
                    await self.backend_pool.close_all()


def create_server(config: ServerConfig) -> PlaywrightMCPServer:
    tools = filtered_tools(config)
    backend_pool = BackendPool(config, tools)
    return _create_server(config, backend_pool)


async def create_connection(
    user_config: dict[str, Any] | ServerConfig | None = None,
    context_getter: Callable[[], Awaitable[PlaywrightBrowserContext] | PlaywrightBrowserContext] | None = None,
) -> PlaywrightMCPServer:
    config = resolve_config(user_config)
    tools = filtered_tools(config)
    backend_pool = BackendPool(config, tools, context_getter=context_getter)
    return _create_server(config, backend_pool)


def _create_server(config: ServerConfig, backend_pool: BackendPool) -> PlaywrightMCPServer:
    tools = backend_pool.tools
    app = FastMCP(name="Playwright", version=_package_version())
    heartbeat_timeout = _ping_timeout_ms()
    if heartbeat_timeout > 0:
        app.add_middleware(HeartbeatMiddleware(backend_pool, timeout_ms=heartbeat_timeout))
    app.add_middleware(BackendSessionCleanupMiddleware(backend_pool))
    app.add_middleware(ValidationMiddleware())

    for tool in tools:
        read_only = tool.tool_type in {"readOnly", "assertion"}
        handler = _make_fastmcp_handler(backend_pool, tool.name)
        signature = tool.signature()
        handler_annotations = {name: parameter.annotation for name, parameter in signature.parameters.items()}
        handler.__signature__ = Signature(
            parameters=[
                *signature.parameters.values(),
                Parameter("_meta", Parameter.KEYWORD_ONLY, annotation=dict[str, Any] | None, default=None),
                Parameter("ctx", Parameter.KEYWORD_ONLY, annotation=FastMCPContext),
            ]
        )
        handler.__annotations__ = handler_annotations
        handler.__annotations__["_meta"] = dict[str, Any] | None
        handler.__annotations__["ctx"] = FastMCPContext
        handler.__annotations__["return"] = Any
        app.tool(
            name=tool.name,
            title=tool.title or _title_from_name(tool.name),
            description=tool.description or tool.name,
            annotations=ToolAnnotations(
                readOnlyHint=read_only,
                destructiveHint=not read_only,
                openWorldHint=True,
            ),
            run_in_thread=False,
        )(handler)

    server = PlaywrightMCPServer(app=app, config=config, backend_pool=backend_pool)
    _register_kill_endpoint(app, server)
    return server


def _register_kill_endpoint(app: FastMCP, server: PlaywrightMCPServer) -> None:
    @app.custom_route("/killkillkill", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])  # type: ignore[arg-type]
    async def _handle_kill(request: Request) -> PlainTextResponse:
        if request.method != "POST" or request.headers.get("x-pw-mcp-kill") != "1":
            return PlainTextResponse("", status_code=405)
        server.trigger_shutdown()
        return PlainTextResponse("Killing process", status_code=200)


class HostAllowlistMiddleware:
    def __init__(self, app: Any, allowed_hosts: list[str] | None, bind_host: str | None) -> None:
        self.app = app
        self.allowed_hosts = allowed_hosts or ([bind_host] if bind_host else ["localhost"])

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and "*" not in self.allowed_hosts:
            headers = dict(scope.get("headers") or [])
            host_header = headers.get(b"host", b"").decode("latin-1")
            host = host_header.rsplit(":", 1)[0] if ":" in host_header else host_header
            if host not in self.allowed_hosts:
                response = PlainTextResponse("Host is not allowed", status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _http_middleware(config: ServerConfig) -> list[Middleware]:
    return [Middleware(HostAllowlistMiddleware, allowed_hosts=config.allowed_hosts, bind_host=config.server_host)]


class BackendPool:
    def __init__(
        self,
        config: ServerConfig,
        tools: list[Any],
        *,
        context_getter: Callable[[], Awaitable[PlaywrightBrowserContext] | PlaywrightBrowserContext] | None = None,
    ) -> None:
        self._config = config
        self._tools = tools
        self._context_getter = context_getter
        self._backends: dict[str, BrowserBackend] = {}
        self._default_key = "__default__"
        self._shared_browser_owner: BrowserBackend | None = None
        self._client_count = 0

    @property
    def tools(self) -> list[Any]:
        return self._tools

    def default_backend(self) -> BrowserBackend:
        backend = self._backends.get(self._default_key)
        if backend is None:
            backend = BrowserBackend(self._config, self._tools)
            self._backends[self._default_key] = backend
        return backend

    async def backend_for(self, key: str | None) -> BrowserBackend:
        key = key or self._default_key
        backend = self._backends.get(key)
        if backend is None:
            supplied_context = await self._supplied_context()
            backend = BrowserBackend(
                self._config,
                self._tools,
                shared_browser_owner=(
                    None
                    if supplied_context is not None
                    else self._shared_owner()
                    if self._uses_shared_browser_owner()
                    else None
                ),
                close_shared_browser=False,
                close_browser_context=not self._config.shared_browser_context and supplied_context is None,
                browser_context=supplied_context,
            )
            self._backends[key] = backend
            self._client_count += 1
        return backend

    async def close(self, key: str | None) -> None:
        key = key or self._default_key
        backend = self._backends.pop(key, None)
        if backend is not None:
            await _close_backend_with_timeout(backend)
            self._client_count = max(0, self._client_count - 1)
        if self._client_count == 0 and self._shared_browser_owner is not None:
            await _close_backend_with_timeout(self._shared_browser_owner)
            self._shared_browser_owner = None

    async def close_all(self) -> None:
        backends = list(self._backends.values())
        self._backends.clear()
        for backend in backends:
            await _close_backend_with_timeout(backend)
        self._client_count = 0
        if self._shared_browser_owner is not None:
            await _close_backend_with_timeout(self._shared_browser_owner)
            self._shared_browser_owner = None

    def _uses_shared_browser_owner(self) -> bool:
        return bool(self._config.shared_browser_context or self._config.browser_isolated)

    def _shared_owner(self) -> BrowserBackend:
        if self._shared_browser_owner is None:
            self._shared_browser_owner = BrowserBackend(self._config, self._tools)
        return self._shared_browser_owner

    async def _supplied_context(self) -> PlaywrightBrowserContext | None:
        if self._context_getter is None:
            return None
        context = self._context_getter()
        if isawaitable(context):
            return cast(PlaywrightBrowserContext, await context)
        return cast(PlaywrightBrowserContext, context)



class ValidationMiddleware(FastMCPMiddleware):
    """Catch pydantic/FastMCP validation errors and return clean MCP errors matching official."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except FastMCPValidationError as exc:
            # FastMCP wraps pydantic call validation; extract underlying detail
            cause = exc.__cause__
            # context.message can be CallToolRequestParams or a Request wrapper
            tool_name = getattr(context.message, "name", None)
            if tool_name is None:
                params = getattr(context.message, "params", None)
                if params is not None:
                    tool_name = getattr(params, "name", "tool")
                else:
                    tool_name = "tool"
            if isinstance(cause, PydanticValidationError):
                # Build a concise message similar to official: one line per field
                lines: list[str] = []
                for err in cause.errors(include_url=False):
                    loc = ".".join(str(p) for p in err.get("loc", []))
                    # loc is like ('target',) or ('fields', 0, 'target')
                    # Simplify: show last part
                    if loc:
                        short = loc.split(".")[-1]
                    else:
                        short = "value"
                    msg = err.get("msg", "")
                    # Map pydantic messages to more readable
                    # e.g. "Missing required keyword only argument" -> "Required"
                    if "Missing required" in msg or err.get("type") == "missing":
                        msg = "Required"
                    elif "Unexpected keyword" in msg or err.get("type") == "unexpected_keyword_argument":
                        # Show as unexpected field
                        msg = f"Unexpected field: {short}"
                        short = "value"
                    elif "Field required" in msg:
                        msg = "Required"
                    lines.append(f"- {short}: {msg}")
                detail = "\n".join(lines) if lines else str(cause)
            else:
                detail = str(cause) if cause else str(exc)
            formatted = f'Invalid arguments for tool "{tool_name}":\n' + detail
            return ToolResult(content=f"### Error\n{formatted}", is_error=True)
        except PydanticValidationError as exc:
            tool_name = getattr(context.message, "name", None)
            if tool_name is None:
                params = getattr(context.message, "params", None)
                if params is not None:
                    tool_name = getattr(params, "name", "tool")
                else:
                    tool_name = "tool"
            lines = []
            for err in exc.errors(include_url=False):
                loc = ".".join(str(p) for p in err.get("loc", []))
                short = loc.split(".")[-1] if loc else "value"
                msg = err.get("msg", "")
                if "Field required" in msg or err.get("type") == "missing":
                    msg = "Required"
                lines.append(f"- {short}: {msg}")
            detail = "\n".join(lines) if lines else str(exc)
            formatted = f'Invalid arguments for tool "{tool_name}":\n' + detail
            return ToolResult(content=f"### Error\n{formatted}", is_error=True)


class HeartbeatMiddleware(FastMCPMiddleware):
    def __init__(self, backend_pool: BackendPool, *, timeout_ms: int, interval_ms: int = 3000) -> None:
        self._backend_pool = backend_pool
        self._timeout_ms = timeout_ms
        self._interval_ms = interval_ms
        self._active_sessions: set[int] = set()
        self._lock = anyio.Lock()

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        fastmcp_context = context.fastmcp_context
        if fastmcp_context is None or fastmcp_context.request_context is None:
            return await call_next(context)

        session = fastmcp_context.session
        session_identity = id(session)
        session_id = _session_id(fastmcp_context)
        async with self._lock:
            if session_identity not in self._active_sessions:
                task_group = getattr(session, "_subscription_task_group", None)
                if task_group is not None:
                    self._active_sessions.add(session_identity)
                    task_group.start_soon(self._heartbeat_loop, session, session_identity, session_id)

        return await call_next(context)

    async def _heartbeat_loop(self, session: Any, session_identity: int, session_id: str | None) -> None:
        try:
            while True:
                await anyio.sleep(self._interval_ms / 1000)
                with anyio.move_on_after(self._timeout_ms / 1000) as scope:
                    await session.send_ping()
                if scope.cancel_called:
                    await self._close_dead_session(session, session_id)
                    return
        except anyio.ClosedResourceError:
            return
        except Exception:
            await self._close_dead_session(session, session_id)
        finally:
            self._active_sessions.discard(session_identity)

    async def _close_dead_session(self, session: Any, session_id: str | None) -> None:
        with anyio.CancelScope(shield=True):
            await self._backend_pool.close(session_id)
        task_group = getattr(session, "_subscription_task_group", None)
        cancel_scope = getattr(task_group, "cancel_scope", None)
        if cancel_scope is not None:
            cancel_scope.cancel()


class BackendSessionCleanupMiddleware(FastMCPMiddleware):
    def __init__(self, backend_pool: BackendPool) -> None:
        self._backend_pool = backend_pool
        self._active_sessions: set[int] = set()
        self._lock = anyio.Lock()

    async def on_message(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        fastmcp_context = context.fastmcp_context
        if fastmcp_context is None or fastmcp_context.request_context is None:
            return await call_next(context)

        session = fastmcp_context.session
        session_identity = id(session)
        session_id = _session_id(fastmcp_context)
        async with self._lock:
            if session_identity not in self._active_sessions:
                task_group = getattr(session, "_subscription_task_group", None)
                if task_group is not None:
                    self._active_sessions.add(session_identity)
                    task_group.start_soon(self._close_when_session_ends, session_identity, session_id)

        return await call_next(context)

    async def _close_when_session_ends(self, session_identity: int, session_id: str | None) -> None:
        try:
            await anyio.sleep_forever()
        finally:
            self._active_sessions.discard(session_identity)
            with anyio.CancelScope(shield=True):
                await self._backend_pool.close(session_id)


def _make_fastmcp_handler(backend_pool: BackendPool, tool_name: str):
    @wraps(_tool_handler)
    async def handler(**kwargs: Any):
        ctx = kwargs.pop("ctx", None)
        meta = kwargs.pop("_meta", None)
        roots = await _list_roots(ctx)
        session_id = _session_id(ctx)
        backend = await backend_pool.backend_for(session_id)
        result = await backend.call_tool(tool_name, kwargs, roots=roots, meta=meta)
        if backend.is_closed:
            await backend_pool.close(session_id)

        return result

    return handler


def _title_from_name(name: str) -> str:
    return name.removeprefix("browser_").replace("_", " ").title()


def _package_version() -> str:
    for pkg in ("camoufox-playwright-mcp", "playwright-python-mcp"):
        try:
            return version(pkg)
        except PackageNotFoundError:
            pass
    return "0.1.4"


def _ping_timeout_ms() -> int:
    value = os.environ.get("PLAYWRIGHT_MCP_PING_TIMEOUT_MS")
    if value is None:
        return 5000
    try:
        return int(value)
    except ValueError:
        return 5000


async def _tool_handler(**_kwargs: Any):
    raise RuntimeError("unreachable")


async def _list_roots(ctx: FastMCPContext | None) -> list[str] | None:
    if ctx is None:
        return None
    try:
        roots = await ctx.list_roots()
    except Exception:
        return None
    result: list[str] = []
    for root in roots:
        uri = str(root.uri)
        if uri.startswith("file://"):
            result.append(unquote(urlparse(uri).path))
    return result


def _session_id(ctx: FastMCPContext | None) -> str | None:
    if ctx is None:
        return None
    value = getattr(ctx, "session_id", None)
    if value:
        return str(value)
    value = getattr(ctx, "client_id", None)
    return str(value) if value else None


async def _close_backend_with_timeout(backend: BrowserBackend) -> None:
    with anyio.move_on_after(15, shield=True):
        await backend.close()
