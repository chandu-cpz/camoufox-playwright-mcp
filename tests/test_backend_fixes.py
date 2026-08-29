from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest

from camoufox_playwright_mcp.backend.browser_backend import (
    _any_process_references_profile,
    _profile_lock_owner_description,
)
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tools.pdf import pdf_tools
from camoufox_playwright_mcp.mcp.config import resolve_config
from camoufox_playwright_mcp.mcp.server import _package_version


def test_package_version_reports_valid() -> None:
    ver = _package_version()
    assert ver in {"0.1.1", "0.1.2", "0.1.3", "0.1.4", "0.1.5"}


def test_proc_scan_safe_on_non_proc_systems(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(os.path, "exists", lambda p: False if str(p) == "/proc" else True)
    assert _any_process_references_profile(tmp_path) is False
    assert _profile_lock_owner_description(tmp_path) == ""


class FakePDFPageFailing:
    async def pdf(self) -> bytes:
        raise RuntimeError("PDF generation is only supported for Headless Chromium")


class FakePDFTab:
    def __init__(self) -> None:
        self.page = FakePDFPageFailing()


class FakePDFContext:
    def __init__(self) -> None:
        self._tab = FakePDFTab()
        self.config = resolve_config()
        self.cwd = Path.cwd()

    async def ensure_tab(self) -> FakePDFTab:
        return self._tab


@pytest.mark.anyio
async def test_pdf_save_graceful_error_on_non_chromium() -> None:
    tools_by_name = {t.name: t for t in pdf_tools}
    context = cast(Context, FakePDFContext())
    resp = Response(context, tool_name="browser_pdf_save", tool_args={})
    await tools_by_name["browser_pdf_save"].handler(context, {}, resp)
    assert any("PDF saving (browser_pdf_save) is only supported on Headless Chromium" in e for e in resp._errors)
