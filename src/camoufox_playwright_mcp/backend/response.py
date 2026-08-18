from __future__ import annotations

import json
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastmcp.tools.base import ToolResult
from mcp.types import ImageContent, TextContent
from PIL import Image

if TYPE_CHECKING:
    from .context import Context
    from .tab import TabHeader


@dataclass(slots=True)
class SnapshotRequest:
    mode: Literal["none", "full", "explicit"]
    target: str | None = None
    root: Any | None = None
    depth: int | None = None
    boxes: bool | None = None
    file_name: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedFile:
    file_name: Path
    relative_name: str
    printable_link: str
    explicit: bool


class Response:
    def __init__(
        self,
        context: Context,
        *,
        tool_name: str,
        tool_args: dict[str, object],
        relative_to: Path | None = None,
        raw: bool = False,
        json_mode: bool = False,
    ) -> None:
        self._context = context
        self.tool_name = tool_name
        self.tool_args = tool_args
        self._client_workspace = relative_to or context.cwd
        self._results: list[str] = []
        self._errors: list[str] = []
        self._code: list[str] = []
        self._snapshot_request: SnapshotRequest | None = None
        self._image_results: list[tuple[bytes, str]] = []
        self._written_files: set[Path] = set()
        self._is_close = False
        self._raw = json_mode or raw
        self._json = json_mode

    def add_text_result(self, text: str) -> None:
        self._results.append(text)

    async def add_result(
        self,
        title: str,
        data: bytes | str,
        *,
        prefix: str,
        ext: str,
        suggested_filename: str | None = None,
    ) -> None:
        if suggested_filename or isinstance(data, bytes):
            from .context import FilenameTemplate

            resolved = await self.resolve_client_file(
                FilenameTemplate(prefix=prefix, ext=ext, suggested_filename=suggested_filename),
                title,
            )
            await self.add_file_result(resolved, data)
        else:
            self.add_text_result(data)

    async def resolve_client_file(self, template, title: str) -> ResolvedFile:
        if template.suggested_filename:
            file_name = await self.resolve_client_filename(template.suggested_filename)
        else:
            file_name = await self._context.output_file(template, origin="llm")
        relative_name = self._compute_relative_to(file_name)
        return ResolvedFile(
            file_name=file_name,
            relative_name=relative_name,
            printable_link=f"- [{title}]({relative_name})",
            explicit=bool(template.suggested_filename),
        )

    async def resolve_client_filename(self, filename: str) -> Path:
        return await self._context.workspace_file(filename, self._client_workspace)

    async def add_file_result(self, resolved_file: ResolvedFile, data: bytes | str | None) -> None:
        await self._write_file(resolved_file, data)
        self.add_text_result(resolved_file.printable_link)

    def add_file_link(self, title: str, file_name: Path) -> None:
        self.add_text_result(f"- [{title}]({self._compute_relative_to(file_name)})")

    async def register_image_result(self, data: bytes, image_type: str) -> None:
        self._image_results.append((data, image_type))

    def add_error(self, error: str) -> None:
        self._errors.append(error)

    def add_code(self, code: str) -> None:
        self._code.append(code)

    def set_include_snapshot(self) -> None:
        self._snapshot_request = SnapshotRequest(mode=_snapshot_mode(self._context.config.snapshot_mode))

    def set_include_full_snapshot(
        self,
        *,
        target: str | None = None,
        root: Any | None = None,
        depth: int | None = None,
        boxes: bool | None = None,
        file_name: str | None = None,
    ) -> None:
        self._snapshot_request = SnapshotRequest(
            mode="explicit",
            target=target,
            root=root,
            depth=depth,
            boxes=boxes,
            file_name=file_name,
        )

    def set_close(self) -> None:
        self._is_close = True

    @property
    def is_close(self) -> bool:
        return self._is_close

    async def serialize(self) -> ToolResult:
        sections: list[tuple[str, list[str], str | None, bool]] = []

        if self._errors:
            sections.append(("Error", self._errors, None, True))
        if self._results:
            sections.append(("Result", self._results, None, False))
        if self._context.config.codegen != "none" and self._code:
            sections.append(("Ran Playwright code", self._code, "python", False))

        tab_snapshot = None
        tab = self._context.current_tab()
        if tab is not None:
            request = self._snapshot_request
            tab_snapshot = await tab.capture_tab_snapshot(
                target=request.target if request else None,
                root=request.root if request else None,
                depth=request.depth if request else None,
                boxes=request.boxes if request else None,
                relative_to=self._client_workspace,
                include_aria=self._snapshot_request is not None and self._snapshot_request.mode != "none",
            )
            tab_headers = [await current.header_snapshot() for current in self._context.tabs()]
            if (
                self._snapshot_request is not None
                and self._snapshot_request.mode != "none"
                or any(header.changed for header in tab_headers)
            ):
                if len(tab_headers) != 1:
                    sections.append(("Open tabs", render_tabs_markdown(tab_headers), None, False))
                current_header = next((header for header in tab_headers if header.current), tab_headers[0])
                page_lines = render_tab_markdown(current_header)
                sections.append(("Page", page_lines, None, False))

        if tab_snapshot is not None and tab_snapshot.modal_states:
            sections.append(("Modal state", render_modal_states(tab_snapshot.modal_states), None, False))

        if tab_snapshot is not None and self._snapshot_request is not None and self._snapshot_request.mode != "none":
            should_write_snapshot = (
                self._snapshot_request.mode != "explicit" or self._snapshot_request.file_name is not None
            )
            if should_write_snapshot:
                from .context import FilenameTemplate

                suggested_filename = self._snapshot_request.file_name
                if suggested_filename == "<auto>":
                    suggested_filename = None
                resolved_file = await self.resolve_client_file(
                    FilenameTemplate(prefix="page", ext="yml", suggested_filename=suggested_filename),
                    "Snapshot",
                )
                await self._write_file(resolved_file, tab_snapshot.aria_snapshot)
                sections.append(("Snapshot", [resolved_file.printable_link], None, False))
            else:
                sections.append(("Snapshot", [tab_snapshot.aria_snapshot], "yaml", False))

        events = self._render_events(tab_snapshot)
        if events:
            sections.append(("Events", events, None, False))

        paused = self._render_paused()
        if paused:
            sections.append(("Paused", paused, None, False))

        await self._enforce_output_budget()
        sections = self._filter_sections(sections)
        text = self._serialize_sections(sections)
        is_error = any(section[3] for section in sections)
        if is_error:
            return ToolResult(content=text, is_error=True)
        if self._image_results and self._context.config.image_responses != "omit":
            return ToolResult(
                content=[TextContent(type="text", text=text), *self._image_content()],
            )
        return ToolResult(content=text)

    def _image_content(self) -> list[ImageContent]:
        import base64

        content: list[ImageContent] = []
        for data, image_type in self._image_results:
            scaled_data = scale_image_to_fit_message(data, image_type)
            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(scaled_data).decode("ascii"),
                    mimeType=f"image/{image_type}",
                )
            )
        return content

    def _serialize_sections(self, sections: list[tuple[str, list[str], str | None, bool]]) -> str:
        if self._json:
            payload: dict[str, object] = {}
            if any(section[3] for section in sections):
                payload["isError"] = True
            for title, content, _codeframe, _is_error in sections:
                if not content:
                    continue
                key = title.lower()
                if key == "snapshot":
                    match = re.match(r"^- \[Snapshot\]\(([^)]+)\)$", content[0].strip())
                    if match:
                        payload[key] = {"file": match.group(1)}
                    else:
                        payload[key] = "\n".join(content)
                else:
                    payload[key] = "\n".join(content)
            return sanitize_unicode(self._context.redact_secrets(json.dumps(payload, indent=2)))

        rendered: list[str] = []
        for title, content, codeframe, _is_error in sections:
            if not content:
                continue
            if self._raw:
                rendered.extend(content)
                continue
            rendered.append(f"### {title}")
            if codeframe:
                rendered.append(f"```{codeframe}")
            rendered.extend(content)
            if codeframe:
                rendered.append("```")
        return sanitize_unicode("\n".join(self._context.redact_secrets("\n".join(rendered)).splitlines()))

    def _filter_sections(
        self,
        sections: list[tuple[str, list[str], str | None, bool]],
    ) -> list[tuple[str, list[str], str | None, bool]]:
        if not self._raw:
            return sections
        allowed = {"Error", "Result", "Snapshot"}
        return [section for section in sections if section[0] in allowed]

    def _render_events(self, tab_snapshot) -> list[str]:
        if tab_snapshot is None:
            return []
        events: list[str] = []
        if tab_snapshot.console_link:
            events.append(f"- New console entries: {tab_snapshot.console_link}")
        for event in tab_snapshot.events:
            if event.get("type") == "download-start":
                events.append(f"- Downloading file {event.get('suggested_filename')} ...")
            elif event.get("type") == "download-finish":
                output_file = event.get("output_file")
                if isinstance(output_file, Path):
                    events.append(
                        f'- Downloaded file {event.get("suggested_filename")} to "{self._compute_relative_to(output_file)}"'
                    )
        return events

    def _render_paused(self) -> list[str]:
        browser_context = getattr(self._context, "browser_context", lambda: None)()
        debugger = getattr(browser_context, "debugger", None)
        if debugger is None:
            return []
        paused_details_api = getattr(debugger, "paused_details", None)
        paused_details = paused_details_api() if callable(paused_details_api) else paused_details_api
        if not paused_details:
            return []

        title = _field(paused_details, "title") or "Paused"
        location = _field(paused_details, "location") or {}
        file_value = _field(location, "file")
        line_value = _field(location, "line")
        location_text = self._compute_relative_to(Path(str(file_value))) if file_value else ""
        if line_value:
            location_text += f":{line_value}"
        return [
            f"- {title} at {location_text}",
            "- Use any tools to explore and interact, resume by calling resume/step-over/pause-at",
        ]

    def _compute_relative_to(self, file_name: Path) -> str:
        import os

        rel = os.path.relpath(file_name, self._client_workspace)
        if os.path.dirname(rel) in {"", "."} and not rel.startswith("."):
            return "./" + rel
        return rel

    async def _write_file(self, resolved_file: ResolvedFile, data: bytes | str | None = None) -> None:
        resolved_file.file_name.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            resolved_file.file_name.write_text(self._context.redact_secrets(data), encoding="utf-8")
        elif data is not None:
            resolved_file.file_name.write_bytes(data)
        self._written_files.add(resolved_file.file_name.resolve())

    async def _enforce_output_budget(self) -> None:
        max_size = self._context.config.output_max_size
        if not max_size:
            return
        output_dir = self._context.output_dir()
        if not output_dir.exists():
            return
        entries = [
            path
            for path in output_dir.rglob("*")
            if path.is_file()
        ]
        total = sum(path.stat().st_size for path in entries)
        if total <= max_size:
            return
        entries.sort(key=lambda path: path.stat().st_mtime)
        for path in entries:
            if total <= max_size:
                break
            if path.resolve() in self._written_files:
                continue
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
            except OSError:
                continue


def render_tab_markdown(tab: TabHeader) -> list[str]:
    lines = [f"- Page URL: {tab.url}"]
    if tab.title:
        lines.append(f"- Page Title: {tab.title}")
    if tab.main_document_status is not None and not (200 <= tab.main_document_status.status <= 299):
        lines.append(
            f"- HTTP status: {tab.main_document_status.status} {tab.main_document_status.status_text}"
        )
    if tab.crashed:
        lines.append("- Page status: crashed")
    if tab.console["errors"] or tab.console["warnings"]:
        lines.append(f"- Console: {tab.console['errors']} errors, {tab.console['warnings']} warnings")
    return lines


def render_tabs_markdown(tabs: list[TabHeader]) -> list[str]:
    if not tabs:
        return ["No open tabs. Navigate to a URL to create one."]
    lines: list[str] = []
    for index, tab in enumerate(tabs):
        current = " (current)" if tab.current else ""
        crashed = " [crashed]" if tab.crashed else ""
        lines.append(f"- {index}:{current} [{tab.title}]({tab.url}){crashed}")
    return lines


def render_modal_states(modal_states: list[dict[str, object]]) -> list[str]:
    if not modal_states:
        return ["- There is no modal state present"]
    lines: list[str] = []
    for state in modal_states:
        cleared_by = state.get("clearedBy")
        if isinstance(cleared_by, dict):
            tool = cleared_by.get("tool", "the matching tool")
            skill = cleared_by.get("skill")
            handler = f"{tool} ({skill})" if skill else str(tool)
        else:
            handler = str(cleared_by or "the matching tool")
        lines.append(f"- [{state.get('description', 'Modal state')}]: can be handled by {handler}")
    return lines


def scale_image_to_fit_message(data: bytes, image_type: str) -> bytes:
    with Image.open(BytesIO(data)) as image:
        width, height = image.size
        pixels = width * height
        shrink = min(1568 / width, 1568 / height, (1.15 * 1024 * 1024 / pixels) ** 0.5)
        if shrink > 1:
            return data
        scaled_size = (max(1, int(width * shrink)), max(1, int(height * shrink)))
        scaled = image.resize(scaled_size, Image.Resampling.LANCZOS)
        output = BytesIO()
        if image_type == "png":
            scaled.save(output, format="PNG")
        else:
            scaled.convert("RGB").save(output, format="JPEG", quality=80)
        return output.getvalue()


def _field(value: object, name: str) -> object | None:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _snapshot_mode(value: str) -> Literal["none", "full"]:
    return "none" if value == "none" else "full"


def sanitize_unicode(text: str) -> str:
    return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
