from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .codegen import python_literal
from .selector_parser import (
    ParsedAttributeSelector,
    ParsedSelectorPart,
    parse_attribute_selector,
    parse_selector,
)


@dataclass(frozen=True, slots=True)
class RegexSource:
    pattern: str
    flags: str = ""


def as_python_locator(selector: str) -> str:
    """Port of upstream `asLocator('python', selector)` for MCP snippets."""
    return as_python_locators(selector, max_output_size=1)[0]


def as_python_locator_description(selector: str) -> str:
    """Port of upstream `asLocatorDescription('python', selector)`."""
    try:
        parts = parse_selector(selector)
        description = _parse_custom_description(parts)
        if description is not None:
            return description
        return _inner_as_locators(parts, max_output_size=1)[0]
    except (ValueError, json.JSONDecodeError):
        return selector


def as_python_locators(selector: str, *, max_output_size: int = 20) -> list[str]:
    try:
        parts = parse_selector(selector)
        return _inner_as_locators(parts, max_output_size=max_output_size)
    except (ValueError, json.JSONDecodeError):
        return [_default_locator(selector)]


def _parse_custom_description(parts: list[ParsedSelectorPart]) -> str | None:
    if not parts:
        return None
    last = parts[-1]
    if last.name != "internal:describe":
        return None
    description = json.loads(str(last.body))
    return description if isinstance(description, str) else None


def _inner_as_locators(parts: list[ParsedSelectorPart], *, is_frame_locator: bool = False, max_output_size: int = 20) -> list[str]:
    tokens: list[list[str]] = []
    next_base = "frame-locator" if is_frame_locator else "page"
    index = 0
    while index < len(parts):
        part = parts[index]
        base = next_base
        next_base = "locator"

        if part.name == "internal:describe":
            index += 1
            continue
        if part.name == "nth":
            if part.body == "0":
                tokens.append([_generate_locator(base, "first", ""), _generate_locator(base, "nth", "0")])
            elif part.body == "-1":
                tokens.append([_generate_locator(base, "last", ""), _generate_locator(base, "nth", "-1")])
            else:
                tokens.append([_generate_locator(base, "nth", str(part.body))])
            index += 1
            continue
        if part.name == "visible":
            body = str(part.body)
            tokens.append([_generate_locator(base, "visible", body), _generate_locator(base, "default", f"visible={body}")])
            index += 1
            continue
        if part.name == "internal:text":
            exact, text = _detect_exact(str(part.body))
            tokens.append([_generate_locator(base, "text", text, {"exact": exact})])
            index += 1
            continue
        if part.name in {"internal:has-text", "internal:has-not-text"}:
            exact, text = _detect_exact(str(part.body))
            if not exact:
                kind = "has-text" if part.name == "internal:has-text" else "has-not-text"
                tokens.append([_generate_locator(base, kind, text, {"exact": exact})])
                index += 1
                continue
        if part.name in {"internal:has", "internal:has-not", "internal:and", "internal:or", "internal:chain"}:
            nested = part.body
            if not isinstance(nested, dict) or not isinstance(nested.get("parsed"), list):
                raise ValueError(f"Malformed nested selector: {part.name}")
            inners = _inner_as_locators(nested["parsed"], max_output_size=max_output_size)
            kind = {
                "internal:has": "has",
                "internal:has-not": "hasNot",
                "internal:and": "and",
                "internal:or": "or",
                "internal:chain": "chain",
            }[part.name]
            tokens.append([_generate_locator(base, kind, inner) for inner in inners])
            index += 1
            continue
        if part.name == "internal:label":
            exact, text = _detect_exact(str(part.body))
            tokens.append([_generate_locator(base, "label", text, {"exact": exact})])
            index += 1
            continue
        if part.name == "internal:role":
            tokens.append([_role_locator(base, parse_attribute_selector(str(part.body)))])
            index += 1
            continue
        if part.name == "internal:testid":
            attr_selector = parse_attribute_selector(str(part.body))
            if not attr_selector.attributes:
                raise ValueError("internal:testid selector has no attributes")
            tokens.append([_generate_locator(base, "test-id", attr_selector.attributes[0].value)])
            index += 1
            continue
        if part.name == "internal:attr":
            attr_selector = parse_attribute_selector(str(part.body))
            if attr_selector.attributes:
                attr = attr_selector.attributes[0]
                exact = bool(attr.case_sensitive)
                if attr.name == "placeholder":
                    tokens.append([_generate_locator(base, "placeholder", attr.value, {"exact": exact})])
                    index += 1
                    continue
                if attr.name == "alt":
                    tokens.append([_generate_locator(base, "alt", attr.value, {"exact": exact})])
                    index += 1
                    continue
                if attr.name == "title":
                    tokens.append([_generate_locator(base, "title", attr.value, {"exact": exact})])
                    index += 1
                    continue
        if part.name == "internal:control" and part.body == "enter-frame":
            if not tokens:
                raise ValueError("Selector cannot start with entering frame")
            last_tokens = tokens[-1]
            transformed = [_chain_locators([token, _generate_locator(base, "frame", "")]) for token in last_tokens]
            last_part = parts[index - 1]
            if last_part.name in {"xpath", "css"}:
                transformed.append(_generate_locator(base, "frame-locator", _stringify_selector_part(last_part)))
                transformed.append(_generate_locator(base, "frame-locator", _stringify_selector_part(last_part, force_engine_name=True)))
            tokens[-1] = transformed
            next_base = "frame-locator"
            index += 1
            continue

        next_part = parts[index + 1] if index + 1 < len(parts) else None
        selector_part = _stringify_selector_part(part)
        locator_part = _generate_locator(base, "default", selector_part)
        if next_part and next_part.name in {"internal:has-text", "internal:has-not-text"}:
            exact, text = _detect_exact(str(next_part.body))
            if not exact:
                kind = "has-text" if next_part.name == "internal:has-text" else "has-not-text"
                next_locator_part = _generate_locator("locator", kind, text, {"exact": exact})
                option_name = "hasText" if next_part.name == "internal:has-text" else "hasNotText"
                combined_part = _generate_locator(base, "default", selector_part, {option_name: text})
                tokens.append([_chain_locators([locator_part, next_locator_part]), combined_part])
                index += 2
                continue

        locator_part_with_engine = None
        if part.name in {"xpath", "css"}:
            locator_part_with_engine = _generate_locator(base, "default", _stringify_selector_part(part, force_engine_name=True))
        tokens.append([token for token in [locator_part, locator_part_with_engine] if token])
        index += 1

    return _combine_tokens(tokens, max_output_size)


def _locator_for_part(part: ParsedSelectorPart) -> str:
    if part.name == "internal:role":
        return _legacy_role_locator(parse_attribute_selector(str(part.body)))
    if part.name == "internal:testid":
        attr_selector = parse_attribute_selector(part.body)
        if not attr_selector.attributes:
            raise ValueError("internal:testid selector has no attributes")
        return f"get_by_test_id({python_literal(attr_selector.attributes[0].value)})"
    if part.name == "internal:text":
        exact, text = _detect_exact(part.body)
        if exact:
            return f"get_by_text({python_literal(text)}, exact=True)"
        return f"get_by_text({python_literal(text)})"
    if part.name == "internal:label":
        exact, text = _detect_exact(part.body)
        if exact:
            return f"get_by_label({python_literal(text)}, exact=True)"
        return f"get_by_label({python_literal(text)})"
    if part.name == "nth":
        if part.body == "0":
            return "first"
        if part.body == "-1":
            return "last"
        return f"nth({part.body})"
    return _default_locator(_stringify_selector_part(part))


def _role_locator(base: str, attr_selector: ParsedAttributeSelector) -> str:
    attrs: list[tuple[str, Any]] = []
    exact = False

    for attr in attr_selector.attributes:
        if attr.name == "name":
            attrs.append(("name", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "description":
            attrs.append(("description", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "include-hidden":
            attrs.append(("include_hidden", attr.value))
        else:
            attrs.append((_to_snake_case(attr.name), attr.value))

    options: dict[str, Any] = {"attrs": []}
    for name, value in attrs:
        if name == "name":
            options["name"] = value
            options["exact"] = exact
        elif name == "description":
            options["description"] = value
            options["exact"] = exact
        else:
            options["attrs"].append((name, value))
    return _generate_locator(base, "role", attr_selector.name, options)


def _generate_locator(base: str, kind: str, body: Any, options: dict[str, Any] | None = None) -> str:
    options = options or {}
    if kind == "default":
        if "hasText" in options:
            return f"locator({_quote(str(body))}, has_text={_text_or_regex(options['hasText'])})"
        if "hasNotText" in options:
            return f"locator({_quote(str(body))}, has_not_text={_text_or_regex(options['hasNotText'])})"
        return f"locator({_quote(str(body))})"
    if kind == "frame-locator":
        return f"frame_locator({_quote(str(body))})"
    if kind == "frame":
        return "content_frame"
    if kind == "nth":
        return f"nth({body})"
    if kind == "first":
        return "first"
    if kind == "last":
        return "last"
    if kind == "visible":
        return f"filter(visible={'True' if body == 'true' else 'False'})"
    if kind == "role":
        attrs: list[str] = []
        if "name" in options:
            attrs.append(f"name={_text_or_regex(options['name'])}")
        if "description" in options:
            attrs.append(f"description={_text_or_regex(options['description'])}")
        if options.get("exact") and ("name" in options or "description" in options):
            attrs.append("exact=True")
        for name, value in options.get("attrs", []):
            attrs.append(f"{_to_snake_case(name)}={_python_value(value)}")
        suffix = ", " + ", ".join(attrs) if attrs else ""
        return f"get_by_role({_quote(str(body))}{suffix})"
    if kind == "has-text":
        return f"filter(has_text={_text_or_regex(body)})"
    if kind == "has-not-text":
        return f"filter(has_not_text={_text_or_regex(body)})"
    if kind == "has":
        return f"filter(has={body})"
    if kind == "hasNot":
        return f"filter(has_not={body})"
    if kind == "and":
        return f"and_({body})"
    if kind == "or":
        return f"or_({body})"
    if kind == "chain":
        return f"locator({body})"
    if kind == "test-id":
        return f"get_by_test_id({_text_or_regex(body)})"
    if kind == "text":
        return _call_with_exact("get_by_text", body, bool(options.get("exact")))
    if kind == "alt":
        return _call_with_exact("get_by_alt_text", body, bool(options.get("exact")))
    if kind == "placeholder":
        return _call_with_exact("get_by_placeholder", body, bool(options.get("exact")))
    if kind == "label":
        return _call_with_exact("get_by_label", body, bool(options.get("exact")))
    if kind == "title":
        return _call_with_exact("get_by_title", body, bool(options.get("exact")))
    raise ValueError(f"Unknown selector kind {kind}")


def _call_with_exact(method: str, body: Any, exact: bool) -> str:
    if isinstance(body, RegexSource):
        return f"{method}({_regex_to_string(body)})"
    if _is_regex_dict(body):
        regex = RegexSource(pattern=str(body["regex"]), flags=str(body.get("flags") or ""))
        return f"{method}({_regex_to_string(regex)})"
    if exact:
        return f"{method}({_quote(str(body))}, exact=True)"
    return f"{method}({_quote(str(body))})"


def _text_or_regex(body: Any) -> str:
    if isinstance(body, RegexSource):
        return _regex_to_string(body)
    if _is_regex_dict(body):
        return _regex_to_string(RegexSource(pattern=str(body["regex"]), flags=str(body.get("flags") or "")))
    return _quote(str(body))


def _python_value(value: Any) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, RegexSource):
        return _regex_to_string(value)
    if _is_regex_dict(value):
        return _regex_to_string(RegexSource(pattern=str(value["regex"]), flags=str(value.get("flags") or "")))
    return _quote(str(value))


def _regex_to_string(regex: RegexSource) -> str:
    pattern = regex.pattern.replace("\\/", "/").replace('"', '\\"')
    suffix = ", re.IGNORECASE" if "i" in regex.flags else ""
    return f're.compile(r"{pattern}"{suffix})'


def _is_regex_dict(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("regex"), str)


def _quote(text: str) -> str:
    return python_literal(text)


def _chain_locators(locators: list[str]) -> str:
    return ".".join(locators)


def _combine_tokens(tokens: list[list[str]], max_output_size: int) -> list[str]:
    if not tokens:
        return [""]
    result: list[str] = []
    current = [""] * len(tokens)

    def visit(index: int) -> bool:
        if index == len(tokens):
            result.append(_chain_locators(current))
            return len(result) < max_output_size
        for token in tokens[index]:
            current[index] = token
            if not visit(index + 1):
                return False
        return True

    visit(0)
    return result


def _legacy_role_locator(attr_selector: ParsedAttributeSelector) -> str:
    attrs: list[tuple[str, Any]] = []
    exact = False

    for attr in attr_selector.attributes:
        if attr.name == "name":
            attrs.append(("name", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "description":
            attrs.append(("description", attr.value))
            exact = attr.case_sensitive
        elif attr.name == "include-hidden":
            attrs.append(("include_hidden", attr.value))
        else:
            attrs.append((_to_snake_case(attr.name), attr.value))

    if exact and any(name in {"name", "description"} for name, _ in attrs):
        attrs.append(("exact", True))

    options = "".join(f", {name}={python_literal(value)}" for name, value in attrs)
    return f"get_by_role({python_literal(attr_selector.name)}{options})"


def _detect_exact(text: str) -> tuple[bool, str | RegexSource]:
    if text.startswith("/") and text.count("/") >= 2:
        last_slash = text.rfind("/")
        return False, RegexSource(pattern=text[1:last_slash], flags=text[last_slash + 1 :])
    if text.endswith('"s'):
        return True, json.loads(text[:-1])
    if text.endswith('"i'):
        return False, json.loads(text[:-1])
    if text.endswith('"'):
        return True, json.loads(text)
    return False, text


def _stringify_selector_part(part: ParsedSelectorPart, *, force_engine_name: bool = False) -> str:
    if part.name == "css":
        return f"css={part.source}" if force_engine_name else part.source
    if part.name == "xpath" and not force_engine_name and (part.source.startswith("//") or part.source.startswith("..")):
        return part.source
    return f"{part.name}={part.source}"


def _default_locator(selector: str) -> str:
    return f"locator({python_literal(selector)})"


def _to_snake_case(value: str) -> str:
    result: list[str] = []
    for char in value:
        if char == "-":
            result.append("_")
        elif char.isupper():
            if result:
                result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result)
