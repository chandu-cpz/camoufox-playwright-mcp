from __future__ import annotations

from pathlib import Path

from camoufox_playwright_mcp.mcp.config import load_config


def test_cli_overrides_env_and_file(monkeypatch, tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text('{"timeouts": {"action": 1000, "navigation": 2000}, "browser": {"browserName": "firefox"}}')
    monkeypatch.setenv("PLAYWRIGHT_MCP_TIMEOUT_NAVIGATION", "45000")
    monkeypatch.setenv("PLAYWRIGHT_MCP_BROWSER", "webkit")

    config = load_config(
        browser="chromium",
        caps="config",
        config_path=config_file,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        timeout_action=9999,
    )

    public = config.as_public_dict()
    assert public["timeouts"]["action"] == 9999
    assert public["timeouts"]["navigation"] == 45000
    assert public["browser"]["browserName"] == "chromium"
    assert public["browser"]["launchOptions"]["channel"] == "chrome-for-testing"


def test_ini_config_resolution(tmp_path: Path) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """
        capabilities = config,storage
        console.level = error
        timeouts.action = 12345
        browser.contextOptions.viewport = 640x480
        browser.contextOptions.bypassCSP = true
        """
    )

    config = load_config(
        browser=None,
        caps="",
        config_path=config_file,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    public = config.as_public_dict()
    assert public["capabilities"] == ["config", "storage"]
    assert public["console"]["level"] == "error"
    assert public["timeouts"]["action"] == 12345
    assert public["browser"]["contextOptions"]["viewport"] == {"width": 640, "height": 480}
    assert public["browser"]["contextOptions"]["bypassCSP"] is True


def test_runtime_fields_include_init_scripts_and_network_filters(tmp_path: Path) -> None:
    init_script = tmp_path / "init.js"
    init_script.write_text("window.__ready = true;", encoding="utf-8")
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        f"""
        browser.initScript = {init_script.name}
        network.allowedOrigins = https://example.com;http://localhost:*
        network.blockedOrigins = https://blocked.example
        """
    )

    config = load_config(
        browser=None,
        caps="config",
        config_path=config_file,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    assert config.init_scripts == [init_script.resolve()]
    assert config.allowed_origins == ["https://example.com", "http://localhost:*"]
    assert config.blocked_origins == ["https://blocked.example"]


def test_remote_endpoint_headers_are_preserved() -> None:
    config = load_config(
        browser=None,
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        endpoint="ws://example.invalid",
        remote_header={"Authorization": "Bearer token"},
    )

    assert config.remote_endpoint == "ws://example.invalid"
    assert config.remote_headers == {"Authorization": "Bearer token"}
    assert config.as_public_dict()["browser"]["remoteHeaders"] == {"Authorization": "Bearer token"}


def test_browser_camoufox_selects_camoufox_provider_without_chromium_defaults() -> None:
    config = load_config(
        browser="camoufox",
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )

    public = config.as_public_dict()
    assert config.browser_provider == "camoufox"
    assert config.browser_name == "firefox"
    assert config.browser_channel is None
    assert public["browser"]["provider"] == "camoufox"
    assert public["browser"]["browserName"] == "firefox"
    assert "channel" not in public["browser"]["launchOptions"]
    assert "chromiumSandbox" not in public["browser"]["launchOptions"]
    assert "args" not in public["browser"]["launchOptions"]
    assert "viewport" not in public["browser"]["contextOptions"]


def test_camoufox_options_are_preserved_from_config_file(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        """
        {
          "browser": {
            "provider": "camoufox",
            "camoufoxOptions": {
              "humanize": true,
              "headless": "virtual",
              "geoip": true,
              "block_webrtc": true
            }
          }
        }
        """,
        encoding="utf-8",
    )

    config = load_config(
        browser=None,
        caps="config",
        config_path=config_file,
        headless=None,
        test_id_attribute="data-testid",
        vision=False,
    )

    assert config.browser_provider == "camoufox"
    assert config.browser_name == "firefox"
    assert config.camoufox_options == {
        "humanize": True,
        "headless": "virtual",
        "geoip": True,
        "block_webrtc": True,
    }
    assert config.browser_context_options == {}


def test_unknown_browser_does_not_fall_back_to_chrome() -> None:
    try:
        load_config(
            browser="camoufox-typo",
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
        )
    except ValueError as exc:
        assert 'Unsupported browser "camoufox-typo"' in str(exc)
    else:
        raise AssertionError("Expected unsupported browser validation error")


def test_camoufox_rejects_unsupported_combinations(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    config_file.write_text(
        '{"browser": {"provider": "camoufox", "launchOptions": {"channel": "chrome"}}}',
        encoding="utf-8",
    )

    try:
        load_config(
            browser=None,
            caps="config",
            config_path=config_file,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
        )
    except ValueError as exc:
        assert "does not support browser.launchOptions.channel" in str(exc)
    else:
        raise AssertionError("Expected unsupported Camoufox channel validation error")

    try:
        load_config(
            browser="camoufox",
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            cdp_endpoint="http://127.0.0.1:9222",
        )
    except ValueError as exc:
        assert "does not support browser.cdpEndpoint" in str(exc)
    else:
        raise AssertionError("Expected unsupported Camoufox CDP validation error")

    try:
        load_config(
            browser="camoufox",
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            extension=True,
        )
    except ValueError as exc:
        assert "does not support extension mode" in str(exc)
    else:
        raise AssertionError("Expected unsupported Camoufox extension validation error")


def test_save_session_config_is_preserved() -> None:
    config = load_config(
        browser=None,
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        save_session=True,
    )

    assert config.save_session is True
    assert config.as_public_dict()["saveSession"] is True


def test_output_mode_defaults_to_file_and_accepts_stdout() -> None:
    default_config = load_config(
        browser=None,
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
    )
    file_config = load_config(
        browser=None,
        caps="config",
        config_path=None,
        headless=True,
        test_id_attribute="data-testid",
        vision=False,
        output_mode="stdout",
    )

    assert default_config.output_mode == "file"
    assert default_config.as_public_dict()["outputMode"] == "file"
    assert file_config.output_mode == "stdout"


def test_isolated_rejects_user_data_dir(tmp_path: Path) -> None:
    try:
        load_config(
            browser=None,
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            isolated=True,
            user_data_dir=str(tmp_path / "profile"),
        )
    except ValueError as exc:
        assert "userDataDir is not supported in isolated mode" in str(exc)
    else:
        raise AssertionError("Expected isolated user data dir validation error")


def test_console_level_validation() -> None:
    try:
        load_config(
            browser=None,
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            console_level="verbose",
        )
    except ValueError as exc:
        assert "console.level must be one of" in str(exc)
    else:
        raise AssertionError("Expected console level validation error")


def test_output_mode_validation() -> None:
    try:
        load_config(
            browser=None,
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            output_mode="json",
        )
    except ValueError as exc:
        assert "outputMode must be one of" in str(exc)
    else:
        raise AssertionError("Expected output mode validation error")


def test_output_dir_rejects_system_directory() -> None:
    try:
        load_config(
            browser=None,
            caps="config",
            config_path=None,
            headless=True,
            test_id_attribute="data-testid",
            vision=False,
            output_dir=Path("/tmp"),
        )
    except ValueError as exc:
        assert "outputDir must not be a system directory" in str(exc)
    else:
        raise AssertionError("Expected output dir validation error")


def test_camoufox_env_vars_precedence(monkeypatch) -> None:
    monkeypatch.setenv("CAMOUFOX_MCP_BROWSER", "firefox")
    monkeypatch.setenv("PLAYWRIGHT_MCP_BROWSER", "chromium")
    monkeypatch.setenv("CAMOUFOX_MCP_HEADLESS", "true")
    monkeypatch.setenv("CAMOUFOX_MCP_TIMEOUT_NAVIGATION", "35000")

    config = load_config(
        browser=None,
        caps="",
        config_path=None,
        headless=None,
        test_id_attribute="data-testid",
        vision=False,
    )

    public = config.as_public_dict()
    assert public["browser"]["browserName"] == "firefox"
    assert public["browser"]["launchOptions"]["headless"] is True
    assert public["timeouts"]["navigation"] == 35000

