from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ParsedSelectorPart:
    name: str
    body: Any
    source: str


@dataclass(slots=True)
class ParsedAttribute:
    name: str
    value: Any
    case_sensitive: bool


@dataclass(slots=True)
class ParsedAttributeSelector:
    name: str
    attributes: list[ParsedAttribute]


NESTED_SELECTOR_NAMES = {"internal:has", "internal:has-not", "internal:and", "internal:or", "internal:chain"}


def parse_selector(selector: str) -> list[ParsedSelectorPart]:
    """Port of upstream selector parsing needed for locator codegen.

    Upstream source:
    - packages/isomorphic/selectorParser.ts
    - parseSelectorString
    """
    parts = [_parse_selector_part(part) for part in _split_selector(selector)]
    if parts and parts[0].name in NESTED_SELECTOR_NAMES:
        raise ValueError(f'"{parts[0].name}" selector cannot be first')
    return parts


def parse_attribute_selector(selector: str) -> ParsedAttributeSelector:
    """Port of upstream `parseAttributeSelector` for normalized selectors."""
    bracket_index = selector.find("[")
    if bracket_index == -1:
        return ParsedAttributeSelector(name=selector, attributes=[])

    name = selector[:bracket_index]
    attributes: list[ParsedAttribute] = []
    index = bracket_index
    while index < len(selector):
        if selector[index].isspace():
            index += 1
            continue
        if selector[index] != "[":
            raise ValueError(f"Unexpected character in attribute selector: {selector[index]}")
        content, index = _read_bracket_content(selector, index)
        attributes.append(_parse_attribute_content(content))
    return ParsedAttributeSelector(name=name, attributes=attributes)


def _split_selector(selector: str) -> list[str]:
    if ">>" not in selector:
        return [selector.strip()]

    result: list[str] = []
    quote: str | None = None
    start = 0
    index = 0
    while index < len(selector):
        char = selector[index]
        if char == "\\" and index + 1 < len(selector):
            index += 2
        elif quote and char == quote:
            quote = None
            index += 1
        elif not quote and char in {"'", '"', "`"}:
            quote = char
            index += 1
        elif not quote and char == ">" and selector[index + 1 : index + 2] == ">":
            result.append(selector[start:index].strip())
            index += 2
            start = index
        else:
            index += 1
    result.append(selector[start:].strip())
    return result


def _parse_selector_part(part: str) -> ParsedSelectorPart:
    equal_index = part.find("=")
    body: Any
    if equal_index != -1 and _is_valid_engine_name(part[:equal_index].strip()):
        name = part[:equal_index].strip()
        body = part[equal_index + 1 :]
    elif len(part) > 1 and part[0] in {"'", '"'} and part[-1] == part[0]:
        name = "text"
        body = part
    elif _is_xpath_body(part):
        name = "xpath"
        body = part
    else:
        name = "css"
        body = part
    source = str(body)
    if name in NESTED_SELECTOR_NAMES:
        try:
            unescaped = json.loads(f"[{body}]")
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed selector: {name}={body}") from exc
        if not isinstance(unescaped, list) or not unescaped or len(unescaped) > 2 or not isinstance(unescaped[0], str):
            raise ValueError(f"Malformed selector: {name}={body}")
        nested_body: dict[str, Any] = {"parsed": parse_selector(unescaped[0])}
        if len(unescaped) == 2:
            nested_body["distance"] = unescaped[1]
        body = nested_body
    return ParsedSelectorPart(name=name, body=body, source=source)


def _read_bracket_content(selector: str, start: int) -> tuple[str, int]:
    quote: str | None = None
    index = start + 1
    while index < len(selector):
        char = selector[index]
        if char == "\\" and index + 1 < len(selector):
            index += 2
        elif quote and char == quote:
            quote = None
            index += 1
        elif not quote and char in {"'", '"'}:
            quote = char
            index += 1
        elif not quote and char == "]":
            return selector[start + 1 : index], index + 1
        else:
            index += 1
    raise ValueError("Unterminated attribute selector")


def _parse_attribute_content(content: str) -> ParsedAttribute:
    equal_index = content.find("=")
    if equal_index == -1:
        return ParsedAttribute(name=content, value=True, case_sensitive=False)

    name = content[:equal_index]
    raw_value = content[equal_index + 1 :]
    case_sensitive = False
    if raw_value.startswith("/") and raw_value.count("/") >= 2:
        last_slash = raw_value.rfind("/")
        value: Any = {"regex": raw_value[1:last_slash], "flags": raw_value[last_slash + 1 :]}
    elif raw_value.endswith(("i", "s")) and raw_value[:-1]:
        case_sensitive = raw_value[-1] == "s"
        value = _parse_plain_attribute_value(raw_value[:-1])
    else:
        value = _parse_plain_attribute_value(raw_value)

    return ParsedAttribute(name=name, value=value, case_sensitive=case_sensitive)


def _parse_plain_attribute_value(raw_value: str) -> Any:
    if raw_value.startswith('"'):
        return json.loads(raw_value)
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    try:
        return int(raw_value)
    except ValueError:
        return raw_value


def _is_valid_engine_name(value: str) -> bool:
    return bool(value) and all(char.isalnum() or char in "_-+:*" for char in value)


def _is_xpath_body(value: str) -> bool:
    stripped = value.lstrip("(")
    return stripped.startswith("//") or value.startswith("..")
