from __future__ import annotations

from typing import Any, Literal, TypedDict

from camoufox_playwright_mcp.backend.codegen import python_call, python_literal
from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.backend.response import Response
from camoufox_playwright_mcp.backend.tab import ResolvedTarget
from camoufox_playwright_mcp.backend.tool import param, tab_tool


class FormField(TypedDict):
    name: str
    target: str
    type: Literal["textbox", "checkbox", "radio", "combobox", "slider"]
    value: str


async def _resolve_fill_target(tab: Any, field: dict[str, Any]) -> ResolvedTarget:
    """Resolve a fill field, falling back to its accessible label on stale refs.

    Re-rendering forms (Greenhouse, keka) shift refs between snapshot and
    action, so a ref that fails to resolve must not fail the whole batch:
    retry by the field's visible label so the write still lands. The fallback
    is restricted to textbox/slider (the value-idempotent types) and prefers
    an exact label match first, then a loose one, so a label repeated across
    template sections (e.g. "Address") resolves to the exact control.
    """
    try:
        return await tab.resolve_target(
            target=field["target"], element=field.get("name")
        )
    except Exception:
        pass
    name = (field.get("name") or "").strip()
    if name and field.get("type") in {"textbox", "slider"} and not name.startswith("<secret>"):
        for exact in (True, False):
            label_locator = tab.page.get_by_label(name, exact=exact)
            if await label_locator.count():
                first = label_locator.first
                return ResolvedTarget(
                    locator=first,
                    code=f"get_by_label({python_literal(name)}, exact={str(exact).lower()})",
                )
    raise ValueError(
        f"Field {name or field['target']!r} not found on the current page; "
        "capture fresh browser evidence."
    )


async def _handle_fill_form(context: Context, params: dict[str, Any], response: Response) -> None:
    tab = await context.ensure_tab()
    skipped: list[str] = []
    for field in params["fields"]:
        resolved = await _resolve_fill_target(tab, field)
        field_type = field["type"]
        value = field["value"]
        if field_type in {"textbox", "slider"}:
            secret = context.lookup_secret(value)
            # Idempotent fill: a textbox already holding the exact value is
            # skipped instead of rewritten. Rewriting identical values churns
            # the page signature (defeating loop guards) and makes flash
            # models re-fill the same fields every turn. The receipt names the
            # skipped fields so the agent stops re-writing them.
            try:
                current = await resolved.locator.input_value()
            except Exception:
                current = None
            if current == secret.value:
                skipped.append(field.get("name") or field["target"])
                continue
            await tab.fill_form_field(resolved, field_type=field_type, value=secret.value)
            response.add_code(f"await page.{resolved.code}.fill({secret.code})")
        elif field_type in {"checkbox", "radio"}:
            await tab.fill_form_field(resolved, field_type=field_type, value=value)
            response.add_code(python_call(resolved.code, "set_checked", value == "true"))
        elif field_type == "combobox":
            await tab.fill_form_field(resolved, field_type=field_type, value=value)
            response.add_code(f"await page.{resolved.code}.select_option(label={python_literal(value)})")
    if skipped:
        response.add_text_result(
            "ALREADY SET (skipped, value unchanged): " + ", ".join(skipped)
        )


form_tools = [
    tab_tool(
        name="browser_fill_form",
        capability="core",
        tool_type="input",
        parameters=(param("fields", list[FormField]),),
        handler=_handle_fill_form,
    )
]
