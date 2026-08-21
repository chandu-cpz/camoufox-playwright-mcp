<div align="center">

# 🦊 Camoufox Playwright MCP

**The Official Playwright MCP Tools, in Python, on the Camoufox Browser**

[![PyPI version](https://img.shields.io/pypi/v/camoufox-playwright-mcp.svg?color=blue)](https://pypi.org/project/camoufox-playwright-mcp/)
[![Python Version](https://img.shields.io/pypi/pyversions/camoufox-playwright-mcp.svg)](https://pypi.org/project/camoufox-playwright-mcp/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Test Suite](https://github.com/chandu-cpz/camoufox-playwright-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/chandu-cpz/camoufox-playwright-mcp/actions)

*An unofficial Python port of Microsoft's official Playwright MCP server, running the [Camoufox](https://github.com/daijro/camoufox) Firefox build as the default browser.*

[Highlights](#-highlights) • [Quickstart](#-quickstart) • [Client Setup](#-mcp-client-configuration) • [Connection Modes](#-browser-modes--connections) • [Configuration](#-configuration-json--ini) • [Tool Reference](#-available-mcp-tools) • [Divergences](#-intentional-python-divergences--limitations)

</div>

---

## ⚡ Highlights

- 🦊 **Camoufox by Default**: Runs [Camoufox](https://github.com/daijro/camoufox), a Firefox build with fingerprint spoofing built in (`navigator.webdriver` masked, canvas/WebGL/audio randomized, hardware details spoofed).
- 🎭 **Unofficial Python Port of the Official Playwright MCP**: Implements the same tools and behavior as Microsoft's `@playwright/mcp` (`browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, `browser_localstorage_*`, etc.), so existing MCP configs carry over. Not affiliated with Microsoft or the Playwright team.
- 🐍 **Python-Native Code Generation**: Emits clean Python Playwright code snippets instead of JavaScript strings:
  ```python
  await page.get_by_role("button", name="Submit").click()
  ```
- 🔄 **Dual Engine Flexibility**: Run `camoufox` by default, or switch to standard Playwright engines (`chromium`, `chrome`, `firefox`, `webkit`), remote CDP endpoints, or browser extensions.
- 🚀 **Zero-Install with `uvx`**: Run on-demand in Claude Desktop, Cursor, Windsurf, Cline, OpenCode, or any MCP client without manual virtualenv management.

---

## 🤔 What this is (and isn't)

This is an unofficial Python port of Microsoft's [`@playwright/mcp`](https://github.com/microsoft/playwright-mcp). It serves the same MCP tools with the same behavior, so you can swap it into an existing config without changing your prompts. The difference is the browser: instead of stock Chromium or Firefox, it launches [Camoufox](https://github.com/daijro/camoufox), a Firefox build with anti-fingerprinting built in.

It is not affiliated with Microsoft or the Playwright team. Browser-level behavior is upstream Camoufox; this port only wires it into the official MCP tool contract.

---

## 🚀 Quickstart

### Run On-Demand with `uvx`

No installation required. Needs Python 3.12+ (`uvx` handles this). The first launch downloads the Camoufox browser (~150MB, one time), so the first tool call can take a few minutes; after that it starts instantly:

```bash
# Run the Camoufox browser in headless mode (recommended for AI agents)
uvx camoufox-playwright-mcp --headless

# Pre-download the browser ahead of time ("all" also installs Playwright browsers)
uvx camoufox-playwright-mcp install-browser all

# Run with visible browser window (headed mode)
uvx camoufox-playwright-mcp

# Switch to standard Chrome / Chromium
uvx camoufox-playwright-mcp --browser chrome --headless

# Enable storage & developer capabilities
uvx camoufox-playwright-mcp --headless --caps=storage,devtools,vision
```

---

## 💻 MCP Client Configuration

### 1. Claude Desktop

Add this to your `claude_desktop_config.json`:

* **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
* **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
* **Linux**: `~/.config/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "camoufox": {
      "command": "uvx",
      "args": [
        "camoufox-playwright-mcp",
        "--headless"
      ]
    }
  }
}
```

---

### 2. Cursor (`~/.cursor/mcp.json`)

Add to your Cursor MCP settings (`Cursor Settings > MCP > Add New MCP Server`):

```json
{
  "mcpServers": {
    "camoufox": {
      "command": "uvx",
      "args": [
        "camoufox-playwright-mcp",
        "--headless"
      ]
    }
  }
}
```

---

### 3. Cline / Roo Code / Windsurf / Zed

```json
{
  "mcpServers": {
    "browser": {
      "command": "uvx",
      "args": [
        "camoufox-playwright-mcp",
        "--headless"
      ]
    }
  }
}
```

---

### 4. OpenCode (`opencode.json`)

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "camoufox": {
      "type": "local",
      "command": ["uvx", "camoufox-playwright-mcp", "--headless"],
      "enabled": true
    }
  }
}
```

---

## 🌐 Transports (stdio & Streamable HTTP)

By default, the server uses **stdio** transport.

Passing `--port` starts a **Streamable HTTP** server listening at `/mcp`:

```bash
uvx camoufox-playwright-mcp --headless --host 127.0.0.1 --port 8931
```

Client configuration for HTTP transport:

```json
{
  "mcpServers": {
    "camoufox": {
      "url": "http://127.0.0.1:8931/mcp"
    }
  }
}
```

---

## 🔌 Browser Modes & Connections

### 1. Persistent Profiles (Default)
By default, the server launches a persistent browser context using an auto-created profile under the user cache directory (`~/.cache/camoufox-playwright-mcp/`), preserving session state, logins, and cookies across runs:

```bash
# Explicit persistent profile directory
uvx camoufox-playwright-mcp --user-data-dir ~/.config/my-browser-profile
```

### 2. Isolated Ephemeral Sessions
Use `--isolated` to run with a temporary, in-memory context that leaves no trace on disk:

```bash
uvx camoufox-playwright-mcp --isolated --headless
```

### 3. Connect to Existing Browser over CDP
Connect to an existing Chromium / Chrome instance started with `--remote-debugging-port=9222`:

```bash
uvx camoufox-playwright-mcp --cdp-endpoint http://localhost:9222
```

### 4. Connect to Bound Playwright Endpoint
Connect to a remote Playwright browser server:

```bash
uvx camoufox-playwright-mcp --endpoint ws://localhost:3000
```

### 5. Playwright Browser Extension Relay
Attach directly to your existing Chrome or Edge browser tabs via the Playwright Browser Extension:

```bash
uvx --from 'camoufox-playwright-mcp[extension]' camoufox-playwright-mcp --extension
```

---

## 🦊 Camoufox Configuration

When running with `--browser camoufox` (default), you can customize Camoufox's browser parameters via a JSON configuration file (`--config config.json`):

```json
{
  "browser": {
    "provider": "camoufox",
    "camoufoxOptions": {
      "geoip": true,
      "humanize": true,
      "os": "windows",
      "block_images": false,
      "fonts": ["Arial", "Calibri", "Times New Roman"]
    }
  }
}
```

### Key Camoufox Options

| Option | Type | Description |
|---|---|---|
| `geoip` | `bool` | Automatically match timezone, locale, and geolocation to your IP or proxy. |
| `humanize` | `bool` | Add natural, human-like mouse movements and keyboard typing delays. |
| `os` | `str` | Target OS to emulate (`"windows"`, `"macos"`, `"linux"`). |
| `block_images` | `bool` | Block images to optimize network bandwidth and speed up scraping. |
| `webrtc_ip` | `str` | Spoof WebRTC local IP address to prevent real IP leaks. |

---

## ⚙️ Configuration (JSON & INI)

Configuration is merged with the following precedence (highest priority last):

1. Built-in defaults (`browser: camoufox`, `action timeout: 5000ms`, `output: file`).
2. JSON or INI configuration file (via `--config` or `CAMOUFOX_MCP_CONFIG`).
3. Environment variables (`CAMOUFOX_MCP_*` or `PLAYWRIGHT_MCP_*`).
4. Explicit CLI arguments.

### INI Configuration Example (`camoufox.ini`)

```ini
capabilities = storage,devtools,vision
console.level = info
timeouts.action = 8000
timeouts.navigation = 45000
browser.contextOptions.viewport = 1280x720
```

Load with:
```bash
uvx camoufox-playwright-mcp --config camoufox.ini
```

---

## 🌐 Environment Variables

All CLI flags can be set via environment variables:

| Variable | Description |
|---|---|
| `CAMOUFOX_MCP_BROWSER` | Default browser (`camoufox`, `chrome`, `chromium`, `firefox`, `webkit`) |
| `CAMOUFOX_MCP_HEADLESS` | Set to `true` or `1` for headless mode |
| `CAMOUFOX_MCP_ISOLATED` | Set to `true` to use ephemeral isolated contexts |
| `CAMOUFOX_MCP_PROXY_SERVER` | Proxy server URL |
| `CAMOUFOX_MCP_CAPS` | Comma-separated list of capabilities (`storage`, `devtools`, `vision`, `pdf`) |
| `CAMOUFOX_MCP_OUTPUT_DIR` | Output directory for artifacts (screenshots, downloads) |
| `CAMOUFOX_MCP_CONFIG` | Path to JSON/INI configuration file |

*(Note: `PLAYWRIGHT_MCP_*` variables are also supported for backward compatibility).*

---

## 🧰 Available MCP Tools

Same tools as the official Playwright MCP server:

### Navigation & Interaction
* `browser_navigate`: Navigate to any URL with automatic wait-for-load.
* `browser_click`: Click elements using locators, coordinates, or semantic text.
* `browser_type`: Fill input fields (fill semantics, Camoufox humanized typing where available).
* `browser_fill_form`: Fill multiple form fields in one call.
* `browser_hover`, `browser_type`, `browser_press_key`: Natural mouse and keyboard interactions.
* `browser_file_upload`: Upload files to file input elements.
* `browser_drag`, `browser_drop`: Perform drag-and-drop operations.

### Inspection & Output
* `browser_snapshot`: Capture full accessibility and semantic tree snapshots.
* `browser_take_screenshot`: Capture full-page or element screenshots.
* `browser_evaluate`: Safely evaluate JavaScript within the page context.
* `browser_console_messages`: Retrieve console logs and error streams.

### Storage & State (Enable with `--caps storage`)
* `browser_localstorage_list`, `browser_localstorage_get`, `browser_localstorage_set`, `browser_localstorage_delete`, `browser_localstorage_clear`
* `browser_sessionstorage_list`, `browser_sessionstorage_get`, `browser_sessionstorage_set`, `browser_sessionstorage_delete`, `browser_sessionstorage_clear`
* `browser_cookies`: Get, set, and clear cookies.
* `browser_storage_state`, `browser_set_storage_state`: Save and restore full storage state files.

### Tabs & Network
* `browser_tabs`: Manage multiple tabs (list, switch, create, close).
* `browser_network`: Manage routing and network interception.
* `browser_handle_dialog`: Accept or dismiss JavaScript alerts, confirms, and prompts.

---

## 🔬 Intentional Python Divergences & Limitations

This server is designed to follow the official Playwright MCP public contract while providing a Python-native experience:

- **Python Code Generation**: Upstream `@playwright/mcp` generates JavaScript snippets; this server generates native Python Playwright snippets (`await page.get_by_role(...).click()`).
- **`browser_run_code_unsafe`**: Executes asynchronous Python Playwright code directly against the active `page` instance.
- **`browser.initPage`**: Accepts Python-native modules defining `init_page(page)` or `default(page)`.
- **`browser_annotate`**: Intentionally omitted (upstream relies on a Node.js dashboard daemon).
- **`browser_pdf_save`**: PDF generation is supported when running Headless Chromium engines (`--browser chromium --headless`).

---

## 🧪 Testing & Conformance

Run local test and quality gates:

```bash
# Lint checks
uv run ruff check .

# Type checking (strict mypy across all source and test files)
uv run mypy src tests

# Unit and integration test suite
uv run pytest
```

Run upstream TypeScript Playwright MCP conformance suite:

```bash
cd tests/conformance/upstream
npm ci
npx playwright test --workers=10
```

---

## 📄 License

Apache License 2.0. See [LICENSE](LICENSE) for details.
