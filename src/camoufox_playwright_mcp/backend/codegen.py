from __future__ import annotations

import json
from typing import Any


def python_literal(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(python_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{python_literal(key)}: {python_literal(item)}" for key, item in value.items()) + "}"
    return json.dumps(str(value))


def python_invocation(
    locator: str,
    method: str,
    options: list[tuple[str, Any]] | None = None,
) -> str:
    if not options:
        return f"await page.{locator}.{method}()"
    rendered = ", ".join(f"{name}={python_literal(value)}" for name, value in options)
    return f"await page.{locator}.{method}({rendered})"


def python_call(subject: str, method: str, argument: Any) -> str:
    return f"await page.{subject}.{method}({python_literal(argument)})"


def python_dict(items: list[tuple[str, Any]]) -> str:
    rendered = ", ".join(f"{python_literal(name)}: {python_literal(value)}" for name, value in items)
    return "{" + rendered + "}"
