from __future__ import annotations

import sys

from camoufox_playwright_mcp import cli
from camoufox_playwright_mcp.mcp import config


def test_install_browser_camoufox_fetches_camoufox(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)

    try:
        cli.main(["install-browser", "camoufox"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected CLI to exit after install-browser")

    assert calls == [[sys.executable, "-m", "camoufox", "fetch"]]


def test_install_browser_default_fetches_camoufox(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)

    try:
        cli.main(["install-browser"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected CLI to exit after install-browser")

    assert calls == [[sys.executable, "-m", "camoufox", "fetch"]]


def test_install_browser_all_fetches_both(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)

    try:
        cli.main(["install-browser", "all"])
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError("Expected CLI to exit after install-browser all")

    assert calls == [
        [sys.executable, "-m", "camoufox", "fetch"],
        [sys.executable, "-m", "playwright", "install"],
    ]


def test_camoufox_browser_rejects_channel(monkeypatch) -> None:
    monkeypatch.setattr(cli, "create_server", lambda _config: None)

    try:
        cli.main(["--browser", "camoufox", "--channel", "chrome"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("Expected CLI to reject Camoufox channel")


def test_parser_defaults() -> None:
    parser = cli.build_parser()
    assert parser.prog == "camoufox-playwright-mcp"
    args = parser.parse_args([])
    assert args.browser is None
    # Verify that resolved config correctly defaults to camoufox
    cfg = config.load_config(
        browser=args.browser,
        caps=args.caps,
        config_path=None,
        headless=args.headless,
        test_id_attribute=args.test_id_attribute,
        vision=args.vision,
    )
    assert cfg.browser_provider == "camoufox"
    assert cfg.browser_name == "firefox"
