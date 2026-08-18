from __future__ import annotations

import json
from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import param, tab_tool


async def _handle_find(context: Context, params: dict[str, Any], response: Response) -> None:
    text = params.get("text")
    regex = params.get("regex")
    if text is None and regex is None:
        response.add_error('Provide either "text" or "regex" to search for.')
        return
    if text is not None and regex is not None:
        response.add_error('Provide only one of "text" or "regex", not both.')
        return

    tab = await context.ensure_tab()
    snapshot = await tab.page.aria_snapshot(mode="ai")
    lines = snapshot.splitlines()
    if regex is not None:
        try:
            query, matched_lines = await _regex_matches(tab.page, str(regex), lines)
        except Exception:
            response.add_error("Invalid regular expression")
            return
    else:
        assert text is not None
        query = json.dumps(text)
        needle = text.lower()
        matched_lines = [index for index, line in enumerate(lines) if needle in line.lower()]
    snippets, match_count = _matching_snippets(lines, matched_lines)
    if match_count:
        response.add_text_result(
            f"Found {match_count} {_plural(match_count, 'match', 'matches')} for {query}:\n\n"
            + "\n\n----\n\n".join(snippets)
        )
    else:
        response.add_text_result(f"No matches found for {query}.")


async def _regex_matches(page: Any, regex: str, lines: list[str]) -> tuple[str, list[int]]:
    result = await page.evaluate(
        """({ source, lines }) => {
            const literal = /^\\/(.*)\\/([a-z]*)$/.exec(source);
            const pattern = literal ? literal[1] : source;
            const flags = literal ? literal[2].replace(/g/g, '') : '';
            const re = new RegExp(pattern, flags);
            const matchedLines = [];
            for (let i = 0; i < lines.length; i++) {
                re.lastIndex = 0;
                if (re.test(lines[i]))
                    matchedLines.push(i);
            }
            return { query: String(re), matchedLines };
        }""",
        {"source": regex, "lines": lines},
    )
    return str(result["query"]), [int(index) for index in result["matchedLines"]]


def _matching_snippets(lines: list[str], matched_lines: list[int]) -> tuple[list[str], int]:
    windows: list[tuple[int, int]] = []
    for index in matched_lines:
        start = max(0, index - 3)
        end = min(len(lines) - 1, index + 3)
        if windows and start <= windows[-1][1] + 1:
            previous_start, previous_end = windows[-1]
            windows[-1] = (previous_start, max(previous_end, end))
        else:
            windows.append((start, end))
    return ["\n".join(lines[start : end + 1]) for start, end in windows], len(matched_lines)


def _plural(count: int, singular: str, plural: str) -> str:
    return singular if count == 1 else plural


find_tools = [
    tab_tool(
        name="browser_find",
        capability="core",
        tool_type="readOnly",
        parameters=(param("text", str | None, None), param("regex", str | None, None)),
        handler=_handle_find,
    )
]
