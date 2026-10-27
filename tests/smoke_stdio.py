"""End-to-end stdio smoke test: initialize + tools/list, no browser launch.

Catches startup regressions (for example signal handlers unsupported on
Windows) before a client ever sees them as a timeout.

The process is terminated once both responses arrive, because shutting the
server down is not what this test is about.

Run with: ``uv run python tests/smoke_stdio.py``
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from typing import Any, TextIO

STARTUP_TIMEOUT_SECONDS = 120
REQUEST_TIMEOUT_SECONDS = 60
TERMINATE_TIMEOUT_SECONDS = 5

INITIALIZE: dict[str, Any] = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "stdio-smoke", "version": "0"},
    },
}
INITIALIZED: dict[str, Any] = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST_TOOLS: dict[str, Any] = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}


class SmokeFailure(Exception):
    pass


def _pump(stream: TextIO, sink: queue.Queue[str | None]) -> None:
    for line in stream:
        sink.put(line)
    sink.put(None)


def _collect(stream: TextIO, sink: list[str]) -> None:
    for line in stream:
        sink.append(line)


def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _await_response(lines: queue.Queue[str | None], request_id: int, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SmokeFailure(f"timed out after {timeout:.0f}s waiting for response {request_id}")
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            raise SmokeFailure(f"timed out after {timeout:.0f}s waiting for response {request_id}") from None
        if line is None:
            raise SmokeFailure(f"server closed stdout before responding to request {request_id}")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            return message


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=TERMINATE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()


def _run() -> int:
    process = subprocess.Popen(
        [sys.executable, "-m", "camoufox_playwright_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    stderr: list[str] = []
    assert process.stdout is not None and process.stderr is not None
    readers = [
        threading.Thread(target=_pump, args=(process.stdout, lines), daemon=True),
        threading.Thread(target=_collect, args=(process.stderr, stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()

    try:
        _send(process, INITIALIZE)
        initialize = _await_response(lines, 1, STARTUP_TIMEOUT_SECONDS)
        if "result" not in initialize:
            raise SmokeFailure(f"initialize failed: {initialize.get('error')}")

        _send(process, INITIALIZED)
        _send(process, LIST_TOOLS)
        listed = _await_response(lines, 2, REQUEST_TIMEOUT_SECONDS)
        if "result" not in listed:
            raise SmokeFailure(f"tools/list failed: {listed.get('error')}")

        tools = listed["result"].get("tools") or []
        if not tools:
            raise SmokeFailure("tools/list returned no tools")

        server_info = initialize["result"].get("serverInfo", {})
        name = server_info.get("name", "unknown")
        version = server_info.get("version", "unknown")
        print(f"OK: {name} {version} served {len(tools)} tools over stdio")
        return 0
    finally:
        _terminate(process)
        for reader in readers:
            reader.join(timeout=1)
        for line in stderr:
            print(line, end="", file=sys.stderr)


def main() -> int:
    try:
        return _run()
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
