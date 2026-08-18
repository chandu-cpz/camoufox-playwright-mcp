from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import websockets

from camoufox_playwright_mcp.backend.extension_relay import CDPRelayServer


def test_extension_relay_bridges_extension_and_cdp() -> None:
    asyncio.run(_exercise_relay())


async def _exercise_relay() -> None:
    relay = CDPRelayServer(cast(Any, object()), browser_channel="chromium")
    await relay.start()
    extension_ready = asyncio.Event()
    extension_task = asyncio.create_task(_fake_extension(relay.extension_endpoint(), extension_ready))
    try:
        await extension_ready.wait()
        async with websockets.connect(relay.cdp_endpoint()) as cdp:
            await cdp.send(json.dumps({"id": 1, "method": "Browser.getVersion"}))
            version = json.loads(await cdp.recv())
            assert version["result"]["product"] == "Chrome/Extension-Bridge"

            await cdp.send(
                json.dumps(
                    {
                        "id": 2,
                        "method": "Target.setAutoAttach",
                        "params": {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True},
                    }
                )
            )
            messages = [json.loads(await cdp.recv()), json.loads(await cdp.recv())]
            assert any(message.get("id") == 2 and message.get("result") == {} for message in messages)
            attached = next(message for message in messages if message.get("method") == "Target.attachedToTarget")
            session_id = attached["params"]["sessionId"]
            assert attached["params"]["targetInfo"]["targetId"] == "target-1"

            await cdp.send(
                json.dumps(
                    {
                        "id": 3,
                        "sessionId": session_id,
                        "method": "Runtime.evaluate",
                        "params": {"expression": "1 + 1"},
                    }
                )
            )
            evaluated = json.loads(await cdp.recv())
            assert evaluated["id"] == 3
            assert evaluated["sessionId"] == session_id
            assert evaluated["result"]["result"]["value"] == 2
    finally:
        extension_task.cancel()
        await relay.stop()
        await asyncio.gather(extension_task, return_exceptions=True)


async def _fake_extension(endpoint: str, extension_ready: asyncio.Event) -> None:
    async with websockets.connect(endpoint) as websocket:
        await websocket.send(
            json.dumps(
                {
                    "method": "chrome.tabs.onCreated",
                    "params": [{"id": 1, "index": 0, "windowId": 1, "url": "about:blank", "active": True, "pinned": False}],
                }
            )
        )
        await websocket.send(json.dumps({"method": "extension.initialized", "params": []}))
        extension_ready.set()
        async for raw_message in websocket:
            message = json.loads(raw_message)
            result: Any = None
            method = message["method"]
            params = message["params"]
            if method == "chrome.debugger.sendCommand" and params[1] == "Target.getTargetInfo":
                result = {
                    "targetInfo": {
                        "targetId": "target-1",
                        "type": "page",
                        "title": "",
                        "url": "about:blank",
                        "attached": False,
                        "canAccessOpener": False,
                    }
                }
            elif method == "chrome.debugger.sendCommand" and params[1] == "Runtime.evaluate":
                result = {"result": {"type": "number", "value": 2}}
            await websocket.send(json.dumps({"id": message["id"], "result": result}))
