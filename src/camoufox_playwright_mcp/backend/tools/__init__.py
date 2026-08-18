from __future__ import annotations

from dataclasses import replace

from camoufox_playwright_mcp.mcp.config import ServerConfig

from ..tool import Tool
from .common import common_tools
from .config import config_tools
from .console import console_tools
from .cookies import cookie_tools
from .devtools import devtools_tools
from .dialogs import dialog_tools
from .evaluate import evaluate_tools
from .files import file_tools
from .find import find_tools
from .form import form_tools
from .keyboard import keyboard_tools
from .metadata import UPSTREAM_TOOL_METADATA
from .mouse import mouse_tools
from .navigate import navigate_tools
from .network import network_tools
from .pdf import pdf_tools
from .route import route_tools
from .run_code import run_code_tools
from .screenshot import screenshot_tools
from .snapshot import snapshot_tools
from .storage import storage_tools
from .tabs import tabs_tools
from .tracing import tracing_tools
from .verify import verify_tools
from .video import video_tools
from .wait import wait_tools
from .webstorage import webstorage_tools


def _apply_upstream_metadata(tool: Tool) -> Tool:
    metadata = UPSTREAM_TOOL_METADATA.get(tool.name)
    if metadata is None:
        return tool
    if tool.title == metadata.title and tool.description == metadata.description:
        return tool
    if tool.title is not None and tool.description is not None:
        return tool
    return replace(
        tool,
        title=tool.title or metadata.title,
        description=tool.description or metadata.description,
    )


IMPLEMENTED_TOOLS = [
    _apply_upstream_metadata(tool)
    for tool in [
        *common_tools,
        *config_tools,
        *console_tools,
        *cookie_tools,
        *dialog_tools,
        *devtools_tools,
        *evaluate_tools,
        *file_tools,
        *find_tools,
        *form_tools,
        *keyboard_tools,
        *mouse_tools,
        *navigate_tools,
        *network_tools,
        *pdf_tools,
        *run_code_tools,
        *route_tools,
        *screenshot_tools,
        *snapshot_tools,
        *storage_tools,
        *tabs_tools,
        *tracing_tools,
        *video_tools,
        *verify_tools,
        *webstorage_tools,
        *wait_tools,
    ]
]


def filtered_tools(config: ServerConfig) -> list[Tool]:
    caps = set(config.caps or [])
    if "tracing" in caps:
        caps.add("devtools")
    return [
        tool
        for tool in IMPLEMENTED_TOOLS
        if not tool.skill_only
        and (tool.capability.startswith("core") or tool.capability in caps)
    ]
