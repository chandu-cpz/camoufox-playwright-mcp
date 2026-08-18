from __future__ import annotations

import json
from typing import Any

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tool import Tool


async def _handle_get_config(context: Context, _params: dict[str, Any], response: Response) -> None:
    response.add_text_result(json.dumps(context.config.as_public_dict(), indent=2))


config_tools = [
    Tool(name="browser_get_config", capability="config", tool_type="readOnly", handler=_handle_get_config),
]
