from __future__ import annotations

import ast
import json
from typing import Any


def locator_or_selector_as_selector(locator: str, *, test_id_attribute: str = "data-testid") -> str:
    """Convert a Python Playwright locator snippet back to a selector.

    This is the Python-native counterpart of upstream `locatorParser.ts` for
    locator forms emitted by this port's locator generator.
    """
    try:
        ast.parse(locator, mode="eval")
    except SyntaxError:
        return locator
    try:
        return _unsafe_locator_as_selector(locator, test_id_attribute=test_id_attribute)
    except ValueError:
        return locator


def _unsafe_locator_as_selector(locator: str, *, test_id_attribute: str) -> str:
    expression = ast.parse(locator, mode="eval").body
    parts = _selector_parts(expression, test_id_attribute=test_id_attribute)
    if not parts:
        raise ValueError("empty locator")
    return " >> ".join(parts)


def _selector_parts(node: ast.AST, *, test_id_attribute: str) -> list[str]:
    if isinstance(node, ast.Name) and node.id == "page":
        return ["page"]

    if isinstance(node, ast.Attribute):
        parts = _selector_parts(node.value, test_id_attribute=test_id_attribute)
        if node.attr == "first":
            return [*parts, "nth=0"]
        if node.attr == "last":
            return [*parts, "nth=-1"]
        if node.attr == "content_frame":
            return [*parts, "internal:control=enter-frame"]
        raise ValueError(f"Unsupported locator attribute: {node.attr}")

    if not isinstance(node, ast.Call):
        raise ValueError("Unsupported locator expression")

    receiver: ast.AST | None = None
    method: str
    if isinstance(node.func, ast.Attribute):
        receiver = node.func.value
        method = node.func.attr
    elif isinstance(node.func, ast.Name):
        method = node.func.id
    else:
        raise ValueError("Unsupported locator callee")

    parts = _selector_parts(receiver, test_id_attribute=test_id_attribute) if receiver is not None else []
    if parts == ["page"]:
        parts = []

    if method == "locator":
        selector = _required_string_arg(node, method)
        if parts:
            return [*parts, selector]
        return [selector]
    if method == "frame_locator":
        selector = _required_string_arg(node, method)
        return [*parts, selector, "internal:control=enter-frame"]
    if method == "get_by_role":
        role = _required_string_arg(node, method)
        attrs: list[str] = []
        exact = _keyword_bool(node, "exact")
        if (name := _keyword_value(node, "name")) is not None:
            attrs.append(f"name={_selector_value(name, exact=exact)}")
        if (description := _keyword_value(node, "description")) is not None:
            attrs.append(f"description={_selector_value(description, exact=exact)}")
        for key, value in _keyword_items(node, exclude={"name", "description", "exact"}):
            attrs.append(f"{_to_camel_or_dash(key)}={_selector_value(value, exact=True)}")
        return [*parts, f"internal:role={role}{''.join(f'[{attr}]' for attr in attrs)}"]
    if method == "get_by_text":
        return [*parts, f"internal:text={_selector_value(_required_arg_value(node, method), exact=_keyword_bool(node, 'exact'))}"]
    if method == "get_by_label":
        return [*parts, f"internal:label={_selector_value(_required_arg_value(node, method), exact=_keyword_bool(node, 'exact'))}"]
    if method == "get_by_test_id":
        return [*parts, f"internal:testid=[{test_id_attribute}={_selector_value(_required_arg_value(node, method), exact=True)}]"]
    if method == "get_by_placeholder":
        return [*parts, f"internal:attr=[placeholder={_selector_value(_required_arg_value(node, method), exact=_keyword_bool(node, 'exact'))}]"]
    if method == "get_by_alt_text":
        return [*parts, f"internal:attr=[alt={_selector_value(_required_arg_value(node, method), exact=_keyword_bool(node, 'exact'))}]"]
    if method == "get_by_title":
        return [*parts, f"internal:attr=[title={_selector_value(_required_arg_value(node, method), exact=_keyword_bool(node, 'exact'))}]"]
    if method == "filter":
        filter_parts = _filter_parts(node, test_id_attribute=test_id_attribute)
        return [*parts, *filter_parts]
    if method == "nth":
        if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, int):
            raise ValueError("nth() requires a constant index")
        return [*parts, f"nth={node.args[0].value}"]
    if method == "and_":
        return [*parts, f"internal:and={_nested_selector_arg(node, test_id_attribute=test_id_attribute)}"]
    if method == "or_":
        return [*parts, f"internal:or={_nested_selector_arg(node, test_id_attribute=test_id_attribute)}"]

    raise ValueError(f"Unsupported locator method: {method}")


def _filter_parts(node: ast.Call, *, test_id_attribute: str) -> list[str]:
    parts: list[str] = []
    for keyword in node.keywords:
        if keyword.arg == "visible":
            value = _constant(keyword.value)
            parts.append(f"visible={'true' if value else 'false'}")
        elif keyword.arg == "has_text":
            parts.append(f"internal:has-text={_selector_value(keyword.value, exact=False)}")
        elif keyword.arg == "has_not_text":
            parts.append(f"internal:has-not-text={_selector_value(keyword.value, exact=False)}")
        elif keyword.arg == "has":
            parts.append(f"internal:has={_nested_selector(keyword.value, test_id_attribute=test_id_attribute)}")
        elif keyword.arg == "has_not":
            parts.append(f"internal:has-not={_nested_selector(keyword.value, test_id_attribute=test_id_attribute)}")
        else:
            raise ValueError(f"Unsupported filter option: {keyword.arg}")
    return parts


def _nested_selector_arg(node: ast.Call, *, test_id_attribute: str) -> str:
    if not node.args:
        raise ValueError("Nested locator argument required")
    selector = " >> ".join(_selector_parts(node.args[0], test_id_attribute=test_id_attribute))
    return json.dumps(selector)


def _nested_selector(node: ast.AST, *, test_id_attribute: str) -> str:
    selector = " >> ".join(_selector_parts(node, test_id_attribute=test_id_attribute))
    return json.dumps(selector)


def _required_string_arg(node: ast.Call, method: str) -> str:
    value = _required_arg_value(node, method)
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise ValueError(f"{method}() requires a string argument")
    return value.value


def _required_arg_value(node: ast.Call, method: str) -> ast.AST:
    if not node.args:
        raise ValueError(f"{method}() requires an argument")
    return node.args[0]


def _keyword_value(node: ast.Call, name: str) -> ast.AST | None:
    for keyword in node.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _keyword_bool(node: ast.Call, name: str) -> bool:
    value = _keyword_value(node, name)
    return bool(_constant(value)) if value is not None else False


def _keyword_items(node: ast.Call, *, exclude: set[str]) -> list[tuple[str, ast.AST]]:
    return [(keyword.arg, keyword.value) for keyword in node.keywords if keyword.arg and keyword.arg not in exclude]


def _selector_value(node: ast.AST, *, exact: bool) -> str:
    if _is_re_compile(node):
        pattern, flags = _regex_parts(node)
        return f"/{pattern}/{'i' if flags else ''}"
    value = _constant(node)
    suffix = "s" if exact else "i"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value)) + suffix


def _regex_parts(node: ast.AST) -> tuple[str, bool]:
    assert isinstance(node, ast.Call)
    if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
        raise ValueError("re.compile() requires a string pattern")
    ignore_case = any(
        isinstance(arg, ast.Attribute) and isinstance(arg.value, ast.Name) and arg.value.id == "re" and arg.attr == "IGNORECASE"
        for arg in node.args[1:]
    )
    return node.args[0].value, ignore_case


def _is_re_compile(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "compile"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "re"
    )


def _constant(node: ast.AST | None) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    raise ValueError("Expected constant locator argument")


def _to_camel_or_dash(value: str) -> str:
    if value == "include_hidden":
        return "include-hidden"
    return value
