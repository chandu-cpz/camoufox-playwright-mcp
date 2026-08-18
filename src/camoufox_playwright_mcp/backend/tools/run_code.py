from __future__ import annotations

import asyncio
import inspect
import json
import textwrap
from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_run_code_unsafe(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    code = params.get("code")
    if params.get("filename"):
        resolved = await response.resolve_client_filename(params["filename"])
        code = resolved.read_text(encoding="utf-8")
    if not code:
        raise ValueError("Either code or filename must be provided")

    response.add_code(code)
    try:
        result = await tab.wait_for_completion(lambda: _execute_python_code(code, tab.page))
    except Exception as exc:
        response.add_error(str(exc))
        return
    if result is not None:
        response.add_text_result(json.dumps(result, separators=(",", ":")))


async def _execute_python_code(code: str, page: Any) -> Any:
    end = asyncio.get_running_loop().create_future()
    namespace: dict[str, Any] = {
        "page": page,
        "__end__": end,
    }
    loop = asyncio.get_running_loop()
    previous_exception_handler = loop.get_exception_handler()

    def exception_handler(_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        exception = context.get("exception")
        if exception is None:
            exception = RuntimeError(str(context.get("message", "Unhandled user-code exception")))
        if not end.done():
            end.set_exception(exception)
        elif previous_exception_handler is not None:
            previous_exception_handler(_loop, context)
        else:
            _loop.default_exception_handler(context)

    loop.set_exception_handler(exception_handler)
    try:
        result = await _execute_in_namespace(code, page, namespace)
        if not end.done():
            end.set_result(result)
        return await end
    finally:
        loop.set_exception_handler(previous_exception_handler)


async def _execute_in_namespace(code: str, page: Any, namespace: dict[str, Any]) -> Any:
    if code.lstrip().startswith("async def "):
        exec(code, namespace, namespace)  # noqa: S102 - this tool is explicitly unsafe.
        fn = namespace.get("run") or namespace.get("__fn__")
        if fn is None:
            candidates = [value for value in namespace.values() if inspect.iscoroutinefunction(value)]
            if not candidates:
                raise ValueError("Python code must define an async function")
            fn = candidates[0]
        return await fn(page)

    function_source = "async def __mcp_run(page):\n" + textwrap.indent(code, "    ")
    exec(function_source, namespace, namespace)  # noqa: S102 - this tool is explicitly unsafe.
    return await namespace["__mcp_run"](page)

run_code_tools = [
    tab_tool(
        name="browser_run_code_unsafe",
        capability="core",
        title="Run Playwright code (unsafe)",
        description=(
            "Run a Python Playwright code snippet. Unsafe: executes arbitrary Python in the Playwright server "
            "process with normal builtins/imports and is RCE-equivalent."
        ),
        parameters=(
            param(
                "code",
                str | None,
                None,
                description=(
                    "Python Playwright code to execute. It may define an async function or provide statements "
                    "that run with page in scope."
                ),
            ),
            param(
                "filename",
                str | None,
                None,
                description="Load code from the specified file. If both code and filename are provided, code will be ignored.",
            ),
        ),
        handler=_handle_run_code_unsafe,
    )
]
