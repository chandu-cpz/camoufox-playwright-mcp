from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from camoufox_playwright_mcp.backend.context import Context
from camoufox_playwright_mcp.mcp.config import ServerConfig


def _context(
    *,
    secrets: dict[str, str] | None = None,
    redact_values: dict[str, str] | None = None,
) -> Context:
    config = ServerConfig(
        secrets=secrets,
        redact_values=redact_values,
    )
    return Context(browser_context=cast(Any, SimpleNamespace()), config=config)


def test_redact_values_are_masked_in_llm_text() -> None:
    cxt = _context(
        redact_values={"OWNER_EMAIL": "owner@example.test"},
    )
    assert cxt.redact_secrets("contact owner@example.test now") == (
        "contact <secret>OWNER_EMAIL</secret> now"
    )


def test_secrets_and_redact_values_are_both_masked() -> None:
    cxt = _context(
        secrets={"DEFAULT_USERNAME": "user@example.test"},
        redact_values={"OWNER_EMAIL": "owner@example.test"},
    )
    out = cxt.redact_secrets("u=user@example.test e=owner@example.test")
    assert "user@example.test" not in out
    assert "owner@example.test" not in out
    assert "<secret>DEFAULT_USERNAME</secret>" in out
    assert "<secret>OWNER_EMAIL</secret>" in out


def test_empty_redact_values_are_skipped() -> None:
    cxt = _context(redact_values={"A": "", "B": None})  # type: ignore[dict-item]
    assert cxt.redact_secrets("just prose with A and B") == "just prose with A and B"


def test_absent_redact_values_leaves_secrets_behavior_unchanged() -> None:
    cxt = _context(secrets={"SECRET": "s3cr3t"})
    assert cxt.redact_secrets("token s3cr3t") == "token <secret>SECRET</secret>"


def test_redact_values_are_not_lookupable() -> None:
    cxt = _context(
        secrets={"DEFAULT_USERNAME": "user@example.test"},
        redact_values={"OWNER_EMAIL": "owner@example.test"},
    )
    cred = cxt.lookup_secret("DEFAULT_USERNAME")
    assert cred.value == "user@example.test"

    owner = cxt.lookup_secret("OWNER_EMAIL")
    assert owner.value == "OWNER_EMAIL"  # name echoed back, not the PII value
