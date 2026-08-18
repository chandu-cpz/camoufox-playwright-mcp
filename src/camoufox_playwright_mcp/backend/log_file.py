from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from camoufox_playwright_mcp.backend.context import FilenameTemplate

if TYPE_CHECKING:
    from camoufox_playwright_mcp.backend.context import Context


@dataclass(slots=True)
class LogChunk:
    file: Path
    from_line: int
    to_line: int
    entry_count: int


class LogFile:
    """Append-only per-tab log with upstream-style chunk links."""

    def __init__(self, context: Context, *, file_prefix: str, title: str) -> None:
        self._context = context
        self._start_time = time() * 1000
        self._file_prefix = file_prefix
        self._title = title
        self._file: Path | None = None
        self._line = 0
        self._entries = 0
        self._last_line = 0
        self._last_entries = 0
        self._stopped = False

    async def append_line(self, wall_time: float, text: str) -> None:
        if self._stopped:
            return
        if self._file is None:
            self._file = await self._context.output_file(
                FilenameTemplate(prefix=self._file_prefix, ext="log"),
                origin="code",
            )
        relative_time = round(wall_time - self._start_time)
        line = f"[{relative_time:>8}ms] {self._context.redact_secrets(text)}\n"
        with self._file.open("a", encoding="utf-8") as file:
            file.write(line)
        self._line += line.count("\n")
        self._entries += 1

    def stop(self) -> None:
        self._stopped = True

    async def take(self, *, relative_to: Path | None = None) -> str | None:
        chunk = await self._take()
        if chunk is None:
            return None
        file_name = chunk.file
        if relative_to is not None:
            file_name = Path(_relative_path(chunk.file, relative_to))
        line_range = f"#L{chunk.from_line}" if chunk.from_line == chunk.to_line else f"#L{chunk.from_line}-L{chunk.to_line}"
        return f"{file_name}{line_range}"

    async def _take(self) -> LogChunk | None:
        if self._file is None or self._entries == self._last_entries:
            return None
        chunk = LogChunk(
            file=self._file,
            from_line=self._last_line + 1,
            to_line=self._line,
            entry_count=self._entries - self._last_entries,
        )
        self._last_line = self._line
        self._last_entries = self._entries
        return chunk


def _relative_path(path: Path, start: Path) -> str:
    try:
        return path.relative_to(start).as_posix()
    except ValueError:
        import os

        return os.path.relpath(path, start)
