from __future__ import annotations

import inspect
from typing import Any, Literal

from camoufox_playwright_mcp.backend.context import Context, FilenameTemplate
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool, param

ActionPosition = Literal["top-left", "top", "top-right", "bottom-left", "bottom", "bottom-right"]
ActionCursor = Literal["none", "pointer"]


async def _handle_start_video(context: Context, params: dict[str, Any], response: Response) -> None:
    await context.ensure_tab()
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(prefix="video", ext="webm", suggested_filename=params.get("filename")),
        "Video",
    )
    await context.start_video_recording(resolved_file.file_name, {"size": params.get("size")})
    response.add_text_result("Video recording started.")


async def _handle_stop_video(context: Context, _params: dict[str, Any], response: Response) -> None:
    file_names = await context.stop_video_recording()
    if not file_names:
        response.add_text_result("No videos were recorded.")
        return
    for file_name in file_names:
        resolved_file = await response.resolve_client_file(
            FilenameTemplate(prefix="video", ext="webm", suggested_filename=str(file_name)),
            "Video",
        )
        await response.add_file_result(resolved_file, None)


async def _handle_video_chapter(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    await tab.page.screencast.show_chapter(
        params["title"],
        description=params.get("description"),
        duration=params.get("duration"),
    )
    response.add_text_result(f"Chapter '{params['title']}' added.")


async def _handle_show_actions(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    show_actions = tab.page.screencast.show_actions
    options = {
        "duration": params.get("duration"),
        "position": params.get("position"),
    }
    if "cursor" in inspect.signature(show_actions).parameters:
        options["cursor"] = params.get("cursor")
    await show_actions(**options)
    response.add_text_result("Action annotations enabled.")


async def _handle_hide_actions(context: Context, _params: dict[str, Any], response: Response) -> None:
    tab = context.current_tab_or_die()
    await tab.page.screencast.hide_actions()
    response.add_text_result("Action annotations disabled.")


video_tools = [
    Tool(
        name="browser_start_video",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("filename", str | None, None), param("size", dict[str, int] | None, None)),
        handler=_handle_start_video,
    ),
    Tool(name="browser_stop_video", capability="devtools", tool_type="readOnly", handler=_handle_stop_video),
    Tool(
        name="browser_video_chapter",
        capability="devtools",
        tool_type="readOnly",
        parameters=(param("title", str), param("description", str | None, None), param("duration", int | float | None, None)),
        handler=_handle_video_chapter,
    ),
    Tool(
        name="browser_video_show_actions",
        capability="devtools",
        tool_type="readOnly",
        parameters=(
            param("duration", int | float | None, None),
            param("position", ActionPosition | None, None),
            param("cursor", ActionCursor | None, None),
        ),
        handler=_handle_show_actions,
    ),
    Tool(name="browser_video_hide_actions", capability="devtools", tool_type="readOnly", handler=_handle_hide_actions),
]
