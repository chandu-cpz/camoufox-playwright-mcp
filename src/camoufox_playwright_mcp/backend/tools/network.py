from __future__ import annotations

import mimetypes
import re
from typing import Any, Literal

from playwright.async_api import Request
from playwright.async_api import Response as PlaywrightResponse

from camoufox_playwright_mcp.backend.codegen import python_literal
from camoufox_playwright_mcp.backend.context import Context, FilenameTemplate
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tab import RequestEntry
from camoufox_playwright_mcp.backend.tool import Tool, param, tab_tool

RequestPart = Literal["request-headers", "request-body", "response-headers", "response-body"]
NetworkState = Literal["online", "offline"]


async def _handle_network_requests(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    all_requests = tab.request_entries()
    filter_pattern = _compile_filter(params.get("filter"))
    lines: list[str] = []
    hidden_static_count = 0

    for index, request in enumerate(all_requests, start=1):
        if not params.get("static", False) and not _is_fetch(request.request) and _is_successful_response(request):
            hidden_static_count += 1
            continue
        if filter_pattern and filter_pattern.search(request.request.url) is None:
            continue
        lines.append(f"{index}. {_render_request_line(request)}")

    if hidden_static_count > 0:
        request_word = "request" if hidden_static_count == 1 else "requests"
        target_word = "it" if hidden_static_count == 1 else "them"
        lines.append(
            f'\nNote: {hidden_static_count} static {request_word} not shown, run with "static" option to see {target_word}.'
        )

    await response.add_result(
        "Network",
        "\n".join(lines),
        prefix="network",
        ext="log",
        suggested_filename=params.get("filename"),
    )


async def _handle_network_request(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    all_requests = tab.request_entries()
    index = params["index"]
    if index < 1 or index > len(all_requests):
        response.add_error(f"Request #{index} not found. Use browser_network_requests to see available indexes.")
        return

    request = all_requests[index - 1]
    part = params.get("part")
    if part:
        await _render_request_part(request, part, response, params.get("filename"))
        return

    await response.add_result(
        "Request",
        _render_request_details(index, request),
        prefix="request",
        ext="log",
        suggested_filename=params.get("filename"),
    )


async def _handle_network_clear(context: Context, _params: dict[str, Any], _response: Response) -> None:
    tab = await context.ensure_tab()
    tab.clear_requests()


async def _handle_network_state_set(context: Context, params: dict[str, Any], response: Response) -> None:
    state = params["state"]
    offline = state == "offline"
    await context.set_offline(offline)
    response.add_text_result(f"Network is now {state}")
    response.add_code(f"await page.context.set_offline({python_literal(offline)})")


def compile_upstream_regex(source: str) -> re.Pattern[str]:
    pattern = source
    flags = 0
    if source.startswith("/"):
        end = _regex_literal_end(source)
        flag_text = source[end + 1 :] if end is not None else ""
        if end is not None and (not flag_text or flag_text.isalpha()):
            pattern = source[1:end]
            for flag in flag_text:
                if flag == "i":
                    flags |= re.IGNORECASE
                elif flag == "m":
                    flags |= re.MULTILINE
                elif flag == "s":
                    flags |= re.DOTALL
                else:
                    raise ValueError(f"Unsupported regular expression flag: {flag}")
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        raise ValueError("Invalid regular expression") from exc


def _compile_filter(value: str | None) -> re.Pattern[str] | None:
    if not value:
        return None
    return compile_upstream_regex(value)


def _regex_literal_end(source: str) -> int | None:
    escaped = False
    in_class = False
    for index, char in enumerate(source[1:], start=1):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "[":
            in_class = True
            continue
        if char == "]":
            in_class = False
            continue
        if char == "/" and not in_class:
            return index
    return None


def _is_successful_response(entry: RequestEntry) -> bool:
    if entry.failure:
        return False
    http_response = entry.response
    return http_response is not None and http_response.status < 400


def _is_fetch(request: Request) -> bool:
    return request.resource_type in {"fetch", "xhr"}


def _render_request_line(entry: RequestEntry) -> str:
    request = entry.request
    response = entry.response
    line = f"[{request.method.upper()}] {_truncate_data_url(request.url)}"
    if response is not None:
        line += f" => [{response.status}] {response.status_text}"
    elif entry.failure:
        line += f" => [FAILED] {entry.failure or 'Unknown error'}"
    return line


def _render_request_details(index: int, entry: RequestEntry) -> str:
    request = entry.request
    http_response = entry.response
    lines: list[str] = [f"#{index} [{request.method.upper()}] {_truncate_data_url(request.url)}", "", "  General"]
    if http_response is not None:
        lines.append(f"    status:    [{http_response.status}] {http_response.status_text}")
    elif entry.failure:
        lines.append(f"    status:    [FAILED] {entry.failure or 'Unknown error'}")
    duration = _compute_duration_ms(request)
    if duration is not None:
        lines.append(f"    duration:  {duration}ms")
    lines.append(f"    type:      {request.resource_type}")
    if http_response is not None:
        content_type = http_response.headers.get("content-type")
        if content_type:
            lines.append(f"    mimeType:  {content_type.split(';', 1)[0].strip()}")

    _append_header_section(lines, "Request headers", request.headers)
    if http_response is not None:
        _append_header_section(lines, "Response headers", http_response.headers)

    hints: list[str] = []
    if request.post_data:
        hints.append('Call browser_network_request with part="request-body" to read the request body.')
    if _can_have_response_body(http_response):
        hints.append('Call browser_network_request with part="response-body" to read the response body.')
    if hints:
        lines.extend(["", *hints])
    return "\n".join(lines)


async def _render_request_part(
    entry: RequestEntry,
    part: RequestPart,
    response: Response,
    suggested_filename: str | None,
) -> None:
    request = entry.request
    if part == "request-headers":
        await response.add_result(
            "Request headers",
            _render_headers(request.headers),
            prefix="request",
            ext="txt",
            suggested_filename=suggested_filename,
        )
        return
    if part == "request-body":
        if request.post_data is not None:
            await response.add_result(
                "Request body",
                request.post_data,
                prefix="request",
                ext="txt",
                suggested_filename=suggested_filename,
            )
        return

    http_response = entry.response
    if http_response is None:
        return
    if part == "response-headers":
        await response.add_result(
            "Response headers",
            _render_headers(http_response.headers),
            prefix="response",
            ext="txt",
            suggested_filename=suggested_filename,
        )
        return

    content_type = http_response.headers.get("content-type", "")
    if _is_textual_mime_type(content_type):
        try:
            text = await http_response.text()
        except Exception:
            return
        await response.add_result(
            "Response body",
            text,
            prefix="response",
            ext="txt",
            suggested_filename=suggested_filename,
        )
        return

    path = await _save_response_body(http_response, response, suggested_filename)
    if path is not None:
        response.add_text_result(path)


def _render_headers(headers: dict[str, str]) -> str:
    return "\n".join(f"{name}: {value}" for name, value in headers.items())


async def _save_response_body(
    http_response: PlaywrightResponse,
    response: Response,
    suggested_filename: str | None,
) -> str | None:
    if not _can_have_response_body(http_response):
        return None
    try:
        body = await http_response.body()
    except Exception:
        return None
    if not body:
        return None
    ext = _extension_for_mime_type(http_response.headers.get("content-type", ""))
    resolved = await response.resolve_client_file(
        FilenameTemplate(prefix="response", ext=ext, suggested_filename=suggested_filename),
        "Response body",
    )
    resolved.file_name.write_bytes(body)
    return resolved.relative_name


def _append_header_section(lines: list[str], title: str, headers: dict[str, str]) -> None:
    if not headers:
        return
    lines.extend(["", f"  {title}"])
    lines.extend(f"    {name}: {value}" for name, value in headers.items())


def _compute_duration_ms(request: Request) -> int | None:
    response_end = request.timing.get("responseEnd")
    if response_end is None or response_end < 0:
        return None
    return round(response_end)


def _can_have_response_body(http_response: PlaywrightResponse | None) -> bool:
    if http_response is None:
        return False
    status = http_response.status
    return status != 204 and status != 304 and not 100 <= status < 200


def _is_textual_mime_type(content_type: str) -> bool:
    mime_type = content_type.split(";", 1)[0].strip().lower()
    return (
        mime_type.startswith("text/")
        or mime_type in {"application/json", "application/javascript", "application/xml", "image/svg+xml"}
        or mime_type.endswith("+json")
        or mime_type.endswith("+xml")
    )


def _extension_for_mime_type(content_type: str) -> str:
    mime_type = content_type.split(";", 1)[0].strip().lower()
    extension = mimetypes.guess_extension(mime_type)
    if extension:
        return extension.lstrip(".")
    return "bin"


def _truncate_data_url(url: str) -> str:
    if not url.startswith("data:") or len(url) <= 80:
        return url
    return url[:77] + "..."


network_tools = [
    tab_tool(
        name="browser_network_requests",
        capability="core",
        tool_type="readOnly",
        title="List network requests",
        description=(
            "Returns a numbered list of network requests since loading the page. Use browser_network_request "
            "with the number to get full details."
        ),
        parameters=(
            param(
                "static",
                bool,
                False,
                description=(
                    "Whether to include successful static resources like images, fonts, scripts, etc. "
                    "Defaults to false."
                ),
            ),
            param(
                "filter",
                str | None,
                None,
                description='Only return requests whose URL matches this regexp (e.g. "/api/.*user").',
            ),
            param(
                "filename",
                str | None,
                None,
                description="Filename to save the network requests to. If not provided, requests are returned as text.",
            ),
        ),
        handler=_handle_network_requests,
    ),
    tab_tool(
        name="browser_network_request",
        capability="core",
        tool_type="readOnly",
        title="Show network request details",
        description=(
            "Returns full details (headers and body) of a single network request, or a single part if `part` "
            "is set. Use the number from browser_network_requests."
        ),
        parameters=(
            param("index", int, description="1-based index of the request, as printed by browser_network_requests."),
            param("part", RequestPart | None, None, description="Return only this part of the request. Omit to return full details."),
            param(
                "filename",
                str | None,
                None,
                description="Filename to save the result to. If not provided, output is returned as text.",
            ),
        ),
        handler=_handle_network_request,
    ),
    tab_tool(
        name="browser_network_clear",
        capability="core",
        tool_type="readOnly",
        title="Clear network requests",
        description="Clear all network requests",
        handler=_handle_network_clear,
        skill_only=True,
    ),
    Tool(
        name="browser_network_state_set",
        capability="network",
        parameters=(param("state", NetworkState),),
        handler=_handle_network_state_set,
    ),
]
