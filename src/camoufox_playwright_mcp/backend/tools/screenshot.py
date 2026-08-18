from __future__ import annotations

from typing import Any, Literal

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context, FilenameTemplate
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool

ImageType = Literal["png", "jpeg"]
ImageScale = Literal["css", "device"]


async def _handle_take_screenshot(context: Context, params: dict[str, Any], response: Response) -> None:
    if params.get("fullPage") and params.get("target"):
        raise ValueError("fullPage cannot be used with element screenshots.")

    tab = await context.ensure_tab()
    file_type: ImageType = params.get("type") or "png"
    scale: ImageScale = params.get("scale") or "css"
    full_page = params.get("fullPage")
    target = None
    if params.get("target"):
        target = await tab.resolve_target(target=params["target"], element=params.get("element"))

    screenshot_options: dict[str, Any] = {
        "type": file_type,
        "scale": scale,
        "timeout": tab.action_timeout,
    }
    if file_type == "jpeg":
        screenshot_options["quality"] = 90
    if full_page is not None:
        screenshot_options["full_page"] = full_page

    if target is not None:
        data = await target.locator.screenshot(**screenshot_options)
    else:
        data = await tab.page.screenshot(**screenshot_options)

    target_label = (params.get("element") or "element") if target is not None else ("full page" if full_page else "viewport")
    resolved_file = await response.resolve_client_file(
        FilenameTemplate(
            prefix="element" if target is not None else "page",
            ext=file_type,
            suggested_filename=params.get("filename") or None,
        ),
        f"Screenshot of {target_label}",
    )

    code_options = {
        key: value
        for key, value in screenshot_options.items()
        if value is not None
    }
    code_options["path"] = resolved_file.relative_name
    response.add_code(f"# Screenshot {target_label} and save it as {resolved_file.relative_name}")
    if target is not None:
        response.add_code(f"await page.{target.code}.screenshot({_python_kwargs(code_options)})")
    else:
        response.add_code(f"await page.screenshot({_python_kwargs(code_options)})")

    await response.add_file_result(resolved_file, data)
    if not params.get("filename"):
        await response.register_image_result(data, file_type)


screenshot_tools = [
    tab_tool(
        name="browser_take_screenshot",
        capability="core",
        tool_type="readOnly",
        parameters=(
            param("target", str | None, None),
            param("element", str | None, None),
            param("type", ImageType, "png"),
            param("filename", str | None, None),
            param("fullPage", bool | None, None),
            param("scale", ImageScale, "css"),
        ),
        handler=_handle_take_screenshot,
    )
]


def _python_kwargs(options: dict[str, Any]) -> str:
    return ", ".join(f"{key}={python_literal(value)}" for key, value in options.items())
