from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastmcp.tools.base import ToolResult

from .context import Context, FilenameTemplate


@dataclass(slots=True)
class SessionLog:
    folder: Path
    cwd: Path

    @classmethod
    async def create(cls, context: Context) -> SessionLog:
        folder_name = f"session-{int(time.time() * 1000)}"
        folder = await context.output_file(
            FilenameTemplate(prefix=folder_name, ext="", suggested_filename=folder_name),
            origin="code",
        )
        folder.mkdir(parents=True, exist_ok=True)
        print(f"Session: {folder}", file=sys.stderr)
        return cls(folder=folder, cwd=context.cwd)

    async def log_response(self, tool_name: str, tool_args: dict[str, Any], response: str | ToolResult) -> None:
        parsed = _parse_response(response, self.cwd)
        parsed.pop("text", None)

        lines = [
            "",
            f"### Tool call: {tool_name}",
            "- Args",
            "```json",
            json.dumps(tool_args, indent=2, default=str),
            "```",
            "- Result",
            "```json",
            json.dumps(parsed, indent=2, default=str),
            "```",
            "",
        ]
        await _append_text(self.folder / "session.md", "\n".join(lines))


async def _append_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(text)


def _parse_response(response: str | ToolResult, cwd: Path) -> dict[str, Any]:
    text = _response_text(response)
    sections = _parse_sections(text)
    payload: dict[str, Any] = {
        "result": sections.get("Result"),
        "error": sections.get("Error"),
        "code": _strip_codeframe(sections.get("Ran Playwright code"), "python"),
        "tabs": sections.get("Open tabs"),
        "page": sections.get("Page"),
        "events": sections.get("Events"),
        "modalState": sections.get("Modal state"),
        "paused": sections.get("Paused"),
        "isError": _response_is_error(response),
        "text": text,
    }

    snapshot = sections.get("Snapshot")
    if snapshot:
        link = _snapshot_link(snapshot)
        if link:
            try:
                payload["snapshot"] = (cwd / link).resolve().read_text(encoding="utf-8")
            except OSError:
                payload["snapshot"] = None
        else:
            payload["inlineSnapshot"] = _strip_codeframe(snapshot, "yaml")

    attachments = _response_attachments(response)
    if attachments:
        payload["attachments"] = attachments
    return {key: value for key, value in payload.items() if value is not None}


def _response_text(response: str | ToolResult) -> str:
    if isinstance(response, str):
        return response
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        first = content[0]
        text = getattr(first, "text", None)
        if isinstance(first, dict):
            text = first.get("text")
        if isinstance(text, str):
            return text
    return ""


def _response_is_error(response: str | ToolResult) -> bool:
    return isinstance(response, ToolResult) and bool(response.is_error)


def _response_attachments(response: str | ToolResult) -> list[Any] | None:
    if isinstance(response, str) or not isinstance(response.content, list) or len(response.content) <= 1:
        return None
    return response.content[1:]


def _parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_title: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("### "):
            if current_title is not None:
                sections[current_title] = "\n".join(current_lines).strip()
            current_title = line[4:]
            current_lines = []
        elif current_title is not None:
            current_lines.append(line)
    if current_title is not None:
        sections[current_title] = "\n".join(current_lines).strip()
    return sections


def _strip_codeframe(value: str | None, language: str) -> str | None:
    if value is None:
        return None
    start = f"```{language}\n"
    if value.startswith(start) and value.endswith("\n```"):
        return value[len(start) : -4]
    return value


def _snapshot_link(snapshot: str) -> str | None:
    marker = "[Snapshot]("
    start = snapshot.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = snapshot.find(")", start)
    return snapshot[start:end] if end != -1 else None
