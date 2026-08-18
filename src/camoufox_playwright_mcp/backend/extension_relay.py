from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import websockets
from playwright.async_api import Playwright
from websockets.asyncio.server import Server, ServerConnection

PLAYWRIGHT_EXTENSION_ID = "mmlmfjhmonkocbjadbfplnigmagldckm"
PLAYWRIGHT_EXTENSION_INSTALL_URL = (
    f"https://chromewebstore.google.com/detail/playwright-extension/{PLAYWRIGHT_EXTENSION_ID}"
)

CDPMessage = dict[str, Any]
SendCommand = Callable[[str, Any], Any]
SendToCDPClient = Callable[[CDPMessage], None]


class CDPRelayServer:
    """Python port of upstream tools/mcp/cdpRelay.ts for --extension."""

    def __init__(
        self,
        playwright: Playwright,
        *,
        browser_channel: str,
        executable_path: str | None = None,
        user_data_dir: Path | None = None,
    ) -> None:
        self._playwright = playwright
        self._browser_channel = browser_channel
        self._executable_path = executable_path
        self._user_data_dir = user_data_dir
        self._server: Server | None = None
        self._ws_host: str | None = None
        self._cdp_path = f"/cdp/{uuid.uuid4()}"
        self._extension_path = f"/extension/{uuid.uuid4()}"
        self._cdp_connection: ServerConnection | None = None
        self._extension_connection: ExtensionConnection | None = None
        self._extension_connected = asyncio.get_running_loop().create_future()
        self._handler = ExtensionProtocolV2(self._send_extension_command)
        self._browser_process: subprocess.Popen[bytes] | None = None

    async def start(self) -> None:
        self._server = await websockets.serve(self._on_connection, "127.0.0.1", 0)
        socket = self._server.sockets[0]
        host, port = socket.getsockname()[:2]
        self._ws_host = f"ws://{host}:{port}"

    def cdp_endpoint(self) -> str:
        if self._ws_host is None:
            raise RuntimeError("Relay server is not started")
        return f"{self._ws_host}{self._cdp_path}"

    def extension_endpoint(self) -> str:
        if self._ws_host is None:
            raise RuntimeError("Relay server is not started")
        return f"{self._ws_host}{self._extension_path}"

    async def establish_extension_connection(self, client_name: str) -> None:
        self._check_extension_installation()
        self._open_connect_page_in_browser(client_name)
        await self._extension_connected
        await self._handler.ready()

    async def stop(self) -> None:
        if self._cdp_connection is not None:
            await self._cdp_connection.close(1000, "Server stopped")
        if self._extension_connection is not None:
            await self._extension_connection.close("Server stopped")
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        if self._browser_process is not None and self._browser_process.poll() is None:
            self._browser_process.terminate()

    async def _on_connection(self, websocket: ServerConnection) -> None:
        if websocket.request is None:
            await websocket.close(4004, "Missing request")
            return
        path = websocket.request.path.split("?", 1)[0]
        if path == self._cdp_path:
            await self._handle_playwright_connection(websocket)
        elif path == self._extension_path:
            await self._handle_extension_connection(websocket)
        else:
            await websocket.close(4004, "Invalid path")

    async def _handle_playwright_connection(self, websocket: ServerConnection) -> None:
        if self._extension_connection is None:
            await websocket.close(1000, "Extension not connected")
            return
        if self._cdp_connection is not None:
            await websocket.close(1000, "Another CDP client already connected")
            return
        self._cdp_connection = websocket

        def send_to_cdp_client(message: CDPMessage) -> None:
            asyncio.create_task(self._send_to_cdp_client(message))

        self._handler.connect_over_cdp(send_to_cdp_client)
        try:
            async for raw_message in websocket:
                await self._handle_playwright_message(json.loads(str(raw_message)))
        finally:
            if self._extension_connection is not None:
                await self._extension_connection.close("Playwright client disconnected")
            self._cdp_connection = None

    async def _handle_extension_connection(self, websocket: ServerConnection) -> None:
        if self._extension_connection is not None:
            await websocket.close(1000, "Another extension connection already established")
            return
        connection = ExtensionConnection(websocket)
        self._extension_connection = connection

        def on_message(method: str, params: Any) -> None:
            self._handler.handle_extension_event(method, params)

        async def on_close(reason: str) -> None:
            self._handler.on_extension_disconnect(reason)
            if self._cdp_connection is not None:
                await self._cdp_connection.close(1000, f"Extension disconnected: {reason}")

        connection.on_message = on_message
        connection.on_close = on_close
        if not self._extension_connected.done():
            self._extension_connected.set_result(None)
        await connection.run()

    async def _handle_playwright_message(self, message: dict[str, Any]) -> None:
        response: CDPMessage
        message_id = message.get("id")
        session_id = message.get("sessionId")
        method = message.get("method")
        params = message.get("params")
        try:
            if not isinstance(method, str):
                raise RuntimeError("CDP message is missing method")
            result = await self._handle_cdp_command(method, params, session_id)
            response = {"id": message_id, "result": result}
            if session_id:
                response["sessionId"] = session_id
        except Exception as exc:
            response = {"id": message_id, "error": {"message": str(exc)}}
            if session_id:
                response["sessionId"] = session_id
        await self._send_to_cdp_client(response)

    async def _handle_cdp_command(self, method: str, params: Any, session_id: str | None) -> Any:
        if method == "Browser.getVersion":
            return {
                "protocolVersion": "1.3",
                "product": "Chrome/Extension-Bridge",
                "userAgent": "CDP-Bridge-Server/1.0.0",
            }
        if method == "Browser.setDownloadBehavior":
            return {}
        handled = await self._handler.handle_cdp_command(method, params, session_id)
        if handled is not None:
            return handled["result"]
        return await self._handler.forward_to_extension(method, params, session_id)

    async def _send_to_cdp_client(self, message: CDPMessage) -> None:
        if self._cdp_connection is not None:
            await self._cdp_connection.send(json.dumps(message))

    async def _send_extension_command(self, method: str, params: Any) -> Any:
        if self._extension_connection is None:
            raise RuntimeError("Extension not connected")
        return await self._extension_connection.send(method, params)

    def _open_connect_page_in_browser(self, client_name: str) -> None:
        href = "chrome-extension://" + PLAYWRIGHT_EXTENSION_ID + "/connect.html?" + urlencode(
            {
                "mcpRelayUrl": self.extension_endpoint(),
                "client": json.dumps({"name": client_name, "version": None}),
                "protocolVersion": os.environ.get("PLAYWRIGHT_EXTENSION_PROTOCOL", "2"),
                **(
                    {"token": token}
                    if (token := os.environ.get("PLAYWRIGHT_MCP_EXTENSION_TOKEN"))
                    else {}
                ),
            }
        )
        executable_path = self._resolve_browser_executable()
        args: list[str] = [executable_path]
        user_data_dir = self._extension_user_data_dir()
        if user_data_dir:
            args.append(f"--user-data-dir={user_data_dir}")
        if sys.platform.startswith("linux") and self._browser_channel in {"chromium", "chrome-for-testing"}:
            args.append("--no-sandbox")
        args.append(href)
        self._browser_process = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def _resolve_browser_executable(self) -> str:
        if self._executable_path:
            return self._executable_path
        channel = self._browser_channel
        if channel in {"chromium", "chrome-for-testing"}:
            return self._playwright.chromium.executable_path
        candidates = {
            "chrome": ["google-chrome", "chrome", "chromium"],
            "chrome-beta": ["google-chrome-beta"],
            "chrome-dev": ["google-chrome-unstable"],
            "chrome-canary": ["google-chrome-canary"],
            "msedge": ["microsoft-edge"],
            "msedge-beta": ["microsoft-edge-beta"],
            "msedge-dev": ["microsoft-edge-dev"],
            "msedge-canary": ["microsoft-edge-canary"],
        }.get(channel, [channel])
        for candidate in candidates:
            if resolved := shutil.which(candidate):
                return resolved
        raise RuntimeError(f'Unsupported channel or executable not found: "{channel}"')

    def _check_extension_installation(self) -> None:
        if self._executable_path:
            return
        user_data_dir = self._extension_user_data_dir()
        if user_data_dir and not _is_playwright_extension_installed(Path(user_data_dir)):
            raise RuntimeError(
                f'Playwright Extension not found in "{user_data_dir}". '
                f"Install it from {PLAYWRIGHT_EXTENSION_INSTALL_URL}"
            )

    def _extension_user_data_dir(self) -> str | None:
        return os.environ.get("PWTEST_EXTENSION_USER_DATA_DIR") or (
            str(self._user_data_dir)
            if self._user_data_dir is not None
            else _default_user_data_dir_for_channel(self._browser_channel)
        )


class ExtensionConnection:
    def __init__(self, websocket: ServerConnection) -> None:
        self._websocket = websocket
        self._callbacks: dict[int, asyncio.Future[Any]] = {}
        self._last_id = 0
        self.on_message: Callable[[str, Any], None] | None = None
        self.on_close: Callable[[str], Any] | None = None

    async def run(self) -> None:
        reason = ""
        try:
            async for raw_message in self._websocket:
                self._handle_message(json.loads(str(raw_message)))
        finally:
            for callback in self._callbacks.values():
                if not callback.done():
                    callback.set_exception(RuntimeError("WebSocket closed"))
            self._callbacks.clear()
            if self.on_close is not None:
                result = self.on_close(reason)
                if asyncio.iscoroutine(result):
                    await result

    async def send(self, method: str, params: Any) -> Any:
        self._last_id += 1
        message_id = self._last_id
        future = asyncio.get_running_loop().create_future()
        self._callbacks[message_id] = future
        await self._websocket.send(json.dumps({"id": message_id, "method": method, "params": params}))
        return await future

    async def close(self, message: str) -> None:
        await self._websocket.close(1000, message)

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_id = message.get("id")
        if message_id and message_id in self._callbacks:
            callback = self._callbacks.pop(message_id)
            if message.get("error"):
                callback.set_exception(RuntimeError(str(message["error"])))
            else:
                callback.set_result(message.get("result"))
            return
        method = message.get("method")
        if method and self.on_message is not None:
            self.on_message(method, message.get("params"))


class ExtensionProtocolV2:
    def __init__(self, send_command: SendCommand) -> None:
        self._model = BrowserModel(send_command)
        self._ready = asyncio.get_running_loop().create_future()

    async def ready(self) -> None:
        await self._ready

    def connect_over_cdp(self, send_to_cdp_client: SendToCDPClient) -> None:
        self._model.connect_over_cdp(send_to_cdp_client)

    def on_extension_disconnect(self, reason: str) -> None:
        if not self._ready.done():
            self._ready.set_exception(RuntimeError(f"Extension disconnected before initialization: {reason}"))

    def handle_extension_event(self, method: str, params: Any) -> None:
        if method == "chrome.debugger.onEvent":
            source, cdp_method, cdp_params = params
            self._model.on_debugger_event(source, cdp_method, cdp_params)
        elif method == "chrome.debugger.onDetach":
            source = params[0]
            self._model.on_debugger_detach(source)
        elif method == "chrome.tabs.onCreated":
            self._model.on_tab_created(params[0])
        elif method == "chrome.tabs.onRemoved":
            self._model.on_tab_removed(params[0])
        elif method == "extension.initialized" and not self._ready.done():
            self._ready.set_result(None)

    async def handle_cdp_command(self, method: str, params: Any, session_id: str | None) -> dict[str, Any] | None:
        if method == "Target.setAutoAttach" and not session_id:
            await self._model.enable_auto_attach()
            return {"result": {}}
        if method == "Target.createTarget":
            return {"result": await self._model.create_target((params or {}).get("url"))}
        if method == "Target.closeTarget":
            return {"result": await self._model.close_target((params or {}).get("targetId"))}
        if method == "Target.getTargetInfo":
            return {"result": self._model.get_target_info(session_id)}
        return None

    async def forward_to_extension(self, method: str, params: Any, session_id: str | None) -> Any:
        if not session_id:
            return await self._model.send_browser_command(method, params)
        return await self._model.send_command(session_id, method, params)


class BrowserModel:
    def __init__(self, send_to_extension: SendCommand) -> None:
        self._send_to_extension = send_to_extension
        self._send_to_cdp_client: SendToCDPClient | None = None
        self._known_tabs: dict[int, dict[str, Any]] = {}
        self._tab_sessions: dict[int, dict[str, Any]] = {}
        self._auto_attach = False
        self._next_session_id = 1

    def connect_over_cdp(self, send_to_cdp_client: SendToCDPClient) -> None:
        self._send_to_cdp_client = send_to_cdp_client

    def on_tab_created(self, tab: dict[str, Any]) -> None:
        tab_id = tab.get("id")
        if tab_id is None:
            return
        self._known_tabs[tab_id] = tab
        if self._auto_attach:
            asyncio.create_task(self._attach_tab(tab_id))

    def on_tab_removed(self, tab_id: int) -> None:
        self._known_tabs.pop(tab_id, None)
        self._detach_tab(tab_id)

    def on_debugger_event(self, source: dict[str, Any], method: str, params: Any) -> None:
        tab_id = source.get("tabId")
        if tab_id is None:
            return
        tab_session = self._tab_sessions.get(tab_id)
        if not tab_session:
            return
        child_session_id = (params or {}).get("sessionId") if isinstance(params, dict) else None
        if method == "Target.attachedToTarget" and child_session_id:
            tab_session["childSessions"].add(child_session_id)
        elif method == "Target.detachedFromTarget" and child_session_id:
            tab_session["childSessions"].discard(child_session_id)
        session_id = source.get("sessionId") or tab_session["sessionId"]
        self._emit({"sessionId": session_id, "method": method, "params": params})

    def on_debugger_detach(self, source: dict[str, Any]) -> None:
        if source.get("tabId") is not None:
            self._detach_tab(source["tabId"])

    async def enable_auto_attach(self) -> None:
        self._auto_attach = True
        await asyncio.gather(*(self._attach_tab(tab_id) for tab_id in list(self._known_tabs)), return_exceptions=True)

    async def create_target(self, url: str | None) -> dict[str, Any]:
        tab = await self._send_to_extension("chrome.tabs.create", [{"url": url}])
        tab_id = tab.get("id") if isinstance(tab, dict) else None
        if tab_id is None:
            raise RuntimeError("Failed to create tab")
        self._known_tabs[tab_id] = tab
        tab_session = await self._attach_tab(tab_id)
        return {"targetId": tab_session.get("targetInfo", {}).get("targetId")}

    async def close_target(self, target_id: str | None) -> dict[str, bool]:
        tab_session = self._find_tab_session(lambda session: session.get("targetInfo", {}).get("targetId") == target_id)
        if not tab_session:
            return {"success": False}
        await self._send_to_extension("chrome.tabs.remove", [tab_session["tabId"]])
        return {"success": True}

    def get_target_info(self, session_id: str | None) -> Any:
        tab_session = self._find_tab_session(lambda session: session["sessionId"] == session_id)
        return tab_session.get("targetInfo") if tab_session else None

    async def send_browser_command(self, method: str, params: Any) -> Any:
        try:
            tab_session: dict[str, Any] = next(iter(self._tab_sessions.values()))
        except StopIteration as exc:
            raise RuntimeError(f"No attached tab to forward browser-level command: {method}") from exc
        return await self._send_to_extension(
            "chrome.debugger.sendCommand",
            [{"tabId": tab_session["tabId"]}, method, params],
        )

    async def send_command(self, session_id: str, method: str, params: Any) -> Any:
        tab_session = self._find_tab_session(lambda session: session["sessionId"] == session_id)
        cdp_session_id = None
        if not tab_session:
            tab_session = self._find_tab_session(lambda session: session_id in session["childSessions"])
            cdp_session_id = session_id
        if not tab_session:
            raise RuntimeError(f"No tab found for sessionId: {session_id}")
        return await self._send_to_extension(
            "chrome.debugger.sendCommand",
            [{"tabId": tab_session["tabId"], "sessionId": cdp_session_id}, method, params],
        )

    async def _attach_tab(self, tab_id: int) -> dict[str, Any]:
        if tab_id in self._tab_sessions:
            return self._tab_sessions[tab_id]
        await self._send_to_extension("chrome.debugger.attach", [{"tabId": tab_id}, "1.3"])
        result = await self._send_to_extension(
            "chrome.debugger.sendCommand",
            [{"tabId": tab_id}, "Target.getTargetInfo"],
        )
        target_info = (result or {}).get("targetInfo")
        session_id = f"pw-tab-{self._next_session_id}"
        self._next_session_id += 1
        tab_session: dict[str, Any] = {
            "tabId": tab_id,
            "sessionId": session_id,
            "targetInfo": target_info,
            "childSessions": set(),
        }
        self._tab_sessions[tab_id] = tab_session
        self._emit(
            {
                "method": "Target.attachedToTarget",
                "params": {
                    "sessionId": session_id,
                    "targetInfo": {**(target_info or {}), "attached": True},
                    "waitingForDebugger": False,
                },
            }
        )
        return tab_session

    def _detach_tab(self, tab_id: int) -> None:
        tab_session = self._tab_sessions.pop(tab_id, None)
        if not tab_session:
            return
        self._emit(
            {
                "method": "Target.detachedFromTarget",
                "params": {
                    "sessionId": tab_session["sessionId"],
                    "targetId": (tab_session.get("targetInfo") or {}).get("targetId"),
                },
            }
        )

    def _emit(self, message: CDPMessage) -> None:
        if self._send_to_cdp_client is not None:
            self._send_to_cdp_client(message)

    def _find_tab_session(self, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
        for session in self._tab_sessions.values():
            if predicate(session):
                return session
        return None


def _default_user_data_dir_for_channel(channel: str) -> str | None:
    home = Path.home()
    if sys.platform.startswith("linux"):
        paths = {
            "chrome": home / ".config" / "google-chrome",
            "chrome-beta": home / ".config" / "google-chrome-beta",
            "chrome-dev": home / ".config" / "google-chrome-unstable",
            "chrome-canary": home / ".config" / "google-chrome-canary",
            "msedge": home / ".config" / "microsoft-edge",
            "msedge-beta": home / ".config" / "microsoft-edge-beta",
            "msedge-dev": home / ".config" / "microsoft-edge-dev",
            "msedge-canary": home / ".config" / "microsoft-edge-canary",
        }
    elif sys.platform == "darwin":
        app_support = home / "Library" / "Application Support"
        paths = {
            "chrome": app_support / "Google" / "Chrome",
            "chrome-beta": app_support / "Google" / "Chrome Beta",
            "chrome-dev": app_support / "Google" / "Chrome Dev",
            "chrome-canary": app_support / "Google" / "Chrome Canary",
            "msedge": app_support / "Microsoft Edge",
            "msedge-beta": app_support / "Microsoft Edge Beta",
            "msedge-dev": app_support / "Microsoft Edge Dev",
            "msedge-canary": app_support / "Microsoft Edge Canary",
        }
    elif sys.platform == "win32":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        paths = {
            "chrome": local_app_data / "Google" / "Chrome" / "User Data",
            "chrome-beta": local_app_data / "Google" / "Chrome Beta" / "User Data",
            "chrome-dev": local_app_data / "Google" / "Chrome Dev" / "User Data",
            "chrome-canary": local_app_data / "Google" / "Chrome SxS" / "User Data",
            "msedge": local_app_data / "Microsoft" / "Edge" / "User Data",
            "msedge-beta": local_app_data / "Microsoft" / "Edge Beta" / "User Data",
            "msedge-dev": local_app_data / "Microsoft" / "Edge Dev" / "User Data",
            "msedge-canary": local_app_data / "Microsoft" / "Edge SxS" / "User Data",
        }
    else:
        paths = {}
    path = paths.get(channel)
    return str(path) if path is not None else None


def _is_playwright_extension_installed(user_data_dir: Path) -> bool:
    try:
        entries = list(user_data_dir.iterdir())
    except OSError:
        return False
    for entry in entries:
        if entry.name != "Default" and not entry.name.startswith("Profile "):
            continue
        if _is_extension_installed_in_profile(entry):
            return True
    return False


def _is_extension_installed_in_profile(profile_dir: Path) -> bool:
    if (profile_dir / "Extensions" / PLAYWRIGHT_EXTENSION_ID).exists():
        return True
    try:
        return f'"{PLAYWRIGHT_EXTENSION_ID}"' in (profile_dir / "Preferences").read_text(encoding="utf-8")
    except OSError:
        return False
