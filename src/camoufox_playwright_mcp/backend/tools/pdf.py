from __future__ import annotations

from typing import Any

from camoufox_playwright_mcp.backend.context import Context, FilenameTemplate
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_pdf_save(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    try:
        data = await tab.page.pdf()
    except Exception as exc:
        msg = str(exc)
        if "PDF generation is only supported for Headless Chromium" in msg or "not supported" in msg.lower():
            response.add_error(
                "PDF saving (browser_pdf_save) is only supported on Headless Chromium. "
                "To save PDFs, run with: --browser chromium --headless"
            )
            return
        raise
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(prefix="page", ext="pdf", suggested_filename=params.get("filename")),
        "Page as pdf",
    )
    await response.add_file_result(resolved_file, data)
    response.add_code(f"await page.pdf(path={resolved_file.relative_name!r})")


pdf_tools = [
    tab_tool(
        name="browser_pdf_save",
        capability="pdf",
        tool_type="readOnly",
        parameters=(param("filename", str | None, None),),
        handler=_handle_pdf_save,
    )
]
