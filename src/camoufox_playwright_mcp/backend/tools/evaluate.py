from __future__ import annotations

import json
from typing import Any

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_evaluate(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    expression = params["function"]
    resolved = None
    if params.get("target") is not None:
        resolved = await tab.resolve_target(target=params["target"], element=params.get("element") or "element")

    async def action() -> None:
        result, is_function, is_undefined = await tab.evaluate(expression, resolved)
        code_expression = expression if is_function else f"() => ({expression})"
        if resolved is not None:
            response.add_code(f"await page.{resolved.code}.evaluate({python_literal(code_expression)})")
        else:
            response.add_code(f"await page.evaluate({python_literal(code_expression)})")
        text = "undefined" if is_undefined else json.dumps(result, indent=2)
        await response.add_result(
            "Evaluation result",
            text,
            prefix="result",
            ext="json",
            suggested_filename=params.get("filename"),
        )

    try:
        await tab.wait_for_completion(action)
    except Exception as exc:
        response.add_error(str(exc))


evaluate_tools = [
    tab_tool(
        name="browser_evaluate",
        capability="core",
        parameters=(
            param("function", str),
            param("target", str | None, None),
            param("element", str | None, None),
            param("filename", str | None, None),
        ),
        handler=_handle_evaluate,
    )
]
