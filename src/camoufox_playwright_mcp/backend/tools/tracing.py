from __future__ import annotations

import time
from typing import Any

from camoufox_playwright_mcp.backend.context import (
    Context,
    FilenameTemplate,
    TraceLegend,
)
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool


async def _handle_start_tracing(context: Context, _params: dict[str, Any], response: Response) -> None:
    if context.trace_legend is not None:
        raise ValueError("Tracing is already started")
    traces_dir = await context.output_file(
        FilenameTemplate(prefix="", ext="", suggested_filename="traces"),
        origin="code",
    )
    traces_dir.mkdir(parents=True, exist_ok=True)
    name = f"trace-{int(time.time() * 1000)}"
    await context.browser_context().tracing.start(name=name, screenshots=True, snapshots=True, live=True)
    context.trace_legend = TraceLegend(traces_dir=traces_dir, name=name)
    response.add_text_result("Trace recording started")
    response.add_file_link("Action log", traces_dir / f"{name}.trace")
    response.add_file_link("Network log", traces_dir / f"{name}.network")
    response.add_file_link("Resources", traces_dir / "resources")


async def _handle_stop_tracing(context: Context, _params: dict[str, Any], response: Response) -> None:
    if context.trace_legend is None:
        raise ValueError("Tracing is not started")
    trace_legend = context.trace_legend
    context.trace_legend = None
    await context.browser_context().tracing.stop()
    response.add_text_result("Trace recording stopped.")
    response.add_file_link("Trace", trace_legend.traces_dir / f"{trace_legend.name}.trace")
    response.add_file_link("Network log", trace_legend.traces_dir / f"{trace_legend.name}.network")
    response.add_file_link("Resources", trace_legend.traces_dir / "resources")


tracing_tools = [
    Tool(name="browser_start_tracing", capability="devtools", tool_type="readOnly", handler=_handle_start_tracing),
    Tool(name="browser_stop_tracing", capability="devtools", tool_type="readOnly", handler=_handle_stop_tracing),
]
