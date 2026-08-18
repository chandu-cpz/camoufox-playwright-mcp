from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from inspect import Parameter, Signature
from types import UnionType
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

from pydantic import Field

if TYPE_CHECKING:
    from .context import Context
    from .response import Response


ToolHandler = Callable[["Context", dict[str, Any], "Response"], Awaitable[None]]
ToolType = Literal["input", "assertion", "action", "readOnly"]
_HIDDEN_LEGACY_FIELDS = {"selector", "startSelector", "endSelector"}


@dataclass(frozen=True, slots=True)
class ToolParameter:
    name: str
    annotation: object
    default: object = Parameter.empty
    description: str | None = None
    hidden: bool = False

    def signature_annotation(self) -> object:
        if self.description is None:
            return self.annotation
        return cast(
            object,
            Annotated[self.annotation, Field(description=self.description)],  # type: ignore[valid-type]  # ty: ignore[invalid-type-form]
        )


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    capability: str
    handler: ToolHandler
    parameters: tuple[ToolParameter, ...] = ()
    title: str | None = None
    description: str | None = None
    tool_type: ToolType = "action"
    skill_only: bool = False
    clears_modal_state: str | None = None
    blocks_on_modal_state: bool = False

    def signature(self) -> Signature:
        return Signature(
            parameters=[
                Parameter(
                    parameter.name,
                    Parameter.KEYWORD_ONLY,
                    default=parameter.default,
                    annotation=parameter.signature_annotation(),
                )
                for parameter in self.parameters
                if not parameter.hidden
            ]
        )

    def validate(self, args: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        parsed: dict[str, Any] = {}
        raw = {key: value for key, value in args.items() if key not in _HIDDEN_LEGACY_FIELDS and key != "_meta"}
        for parameter in self.parameters:
            if parameter.name not in raw:
                if parameter.default is Parameter.empty:
                    errors.append(f"- {parameter.name}: Required")
                else:
                    parsed[parameter.name] = parameter.default
                continue
            value = raw[parameter.name]
            error = _validate_type(value, parameter.annotation)
            if error:
                errors.append(f"- {parameter.name}: {error}")
            else:
                parsed[parameter.name] = value
        if errors:
            raise ToolValidationError("\n".join(errors))
        return parsed


def param(
    name: str,
    annotation: object,
    default: object = Parameter.empty,
    *,
    description: str | None = None,
    hidden: bool = False,
) -> ToolParameter:
    return ToolParameter(
        name=name,
        annotation=annotation,
        default=default,
        description=description,
        hidden=hidden,
    )


def tab_tool(*args: Any, **kwargs: Any) -> Tool:
    kwargs["blocks_on_modal_state"] = True
    return Tool(*args, **kwargs)


class ToolValidationError(ValueError):
    pass


def _validate_type(value: Any, annotation: object) -> str | None:
    if annotation is Any or annotation is object:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {UnionType, Union}:
        if any(_validate_type(value, option) is None for option in args):
            return None
        return f"Expected {_type_name(annotation)}, received {_value_name(value)}"
    if origin is Literal:
        if value in args:
            return None
        allowed = ", ".join(repr(item) for item in args)
        return f"Expected one of {allowed}, received {value!r}"
    if origin is list:
        if not isinstance(value, list):
            return f"Expected list, received {_value_name(value)}"
        item_type = args[0] if args else Any
        for index, item in enumerate(value):
            error = _validate_type(item, item_type)
            if error:
                return f"Item {index}: {error}"
        return None
    if origin is dict:
        if not isinstance(value, dict):
            return f"Expected object, received {_value_name(value)}"
        key_type, value_type = args if len(args) == 2 else (Any, Any)
        for key, item in value.items():
            key_error = _validate_type(key, key_type)
            if key_error:
                return f"Key {key!r}: {key_error}"
            value_error = _validate_type(item, value_type)
            if value_error:
                return f"{key!r}: {value_error}"
        return None
    if annotation is None or annotation is type(None):
        return None if value is None else f"Expected null, received {_value_name(value)}"
    if annotation is bool:
        return None if isinstance(value, bool) else f"Expected boolean, received {_value_name(value)}"
    if annotation is int:
        if isinstance(value, int) and not isinstance(value, bool):
            return None
        return f"Expected integer, received {_value_name(value)}"
    if annotation is float:
        if isinstance(value, int | float) and not isinstance(value, bool):
            return None
        return f"Expected number, received {_value_name(value)}"
    if annotation is str:
        return None if isinstance(value, str) else f"Expected string, received {_value_name(value)}"
    if is_typeddict(annotation):
        return _validate_typed_dict(value, annotation)
    if isinstance(annotation, type):
        if isinstance(value, annotation):
            return None
        return f"Expected {annotation.__name__}, received {_value_name(value)}"
    return None


def _validate_typed_dict(value: Any, annotation: Any) -> str | None:
    if not isinstance(value, dict):
        return f"Expected object, received {_value_name(value)}"
    hints = get_type_hints(annotation)
    for key in getattr(annotation, "__required_keys__", set(hints)):
        if key not in value:
            return f"{key}: Required"
    for key, item_type in hints.items():
        if key not in value:
            continue
        error = _validate_type(value[key], item_type)
        if error:
            return f"{key}: {error}"
    return None


def _type_name(annotation: object) -> str:
    origin = get_origin(annotation)
    if origin in {UnionType, Union}:
        return " or ".join(_type_name(arg) for arg in get_args(annotation))
    if annotation is type(None):
        return "null"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


def _value_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
