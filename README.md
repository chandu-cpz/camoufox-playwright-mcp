<div align="center">

# 🦊 Camoufox Playwright MCP

**The Stealth, Anti-Detect Browser Automation Server for AI Agents**

[![PyPI version](https://img.shields.io/pypi/v/camoufox-playwright-mcp.svg?color=blue)](https://pypi.org/project/camoufox-playwright-mcp/)
[![Python Version](https://img.shields.io/pypi/pyversions/camoufox-playwright-mcp.svg)](https://pypi.org/project/camoufox-playwright-mcp/)
[![License](https://img.shields.io/badge/License-Apache_2.0-green.svg)](https://opensource.org/licenses/Apache-2.0)
[![Test Suite](https://github.com/chandu-cpz/camoufox-playwright-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/chandu-cpz/camoufox-playwright-mcp/actions)

*A Python-native port of Microsoft's official Playwright MCP server — supercharged with Camoufox's custom anti-detect browser engine.*

[Highlights](#-highlights) • [Quickstart](#-quickstart) • [Client Setup](#-mcp-client-configuration) • [Why Camoufox?](#-why-camoufox-mcp-vs-standard-playwright-mcp) • [Connection Modes](#-browser-modes--connections) • [Configuration](#-configuration-json--ini) • [Tool Reference](#-available-mcp-tools) • [Divergences](#-intentional-python-divergences--limitations)

</div>

---

## ⚡ Highlights

- 🥷 **Stealth by Default**: Uses [Camoufox](https://github.com/daijro/camoufox) to mask `navigator.webdriver`, spoof hardware concurrency, randomize canvas/WebGL/audio fingerprints, and bypass anti-bot shields (Cloudflare Turnstile, DataDome, Akamai, etc.).
- 🎭 **100% Official Tool Parity**: Complete 1:1 drop-in replacement for `@playwright/mcp` (`browser_navigate`, `browser_click`, `browser_fill`, `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, `browser_localstorage_*`, etc.).
- 🐍 **Python-Native Code Generation**: Emits clean Python Playwright code snippets instead of JavaScript strings:
  ```python
  await page.get_by_role("button", name="Submit").click()
  ```
- 🔄 **Dual Engine Flexibility**: Run stealth `camoufox` by default, or switch seamlessly to standard Playwright engines (`chromium`, `chrome`, `firefox`, `webkit`), remote CDP endpoints, or browser extensions.
- 🚀 **Zero-Install with `uvx`**: Run on-demand in Claude Desktop, Cursor, Windsurf, Cline, OpenCode, or any MCP client without manual virtualenv management.

---

## ⚔️ Why Camoufox MCP vs Standard Playwright MCP?

When AI agents browse the web using standard automation servers, they are immediately flagged and blocked by Cloudflare Turnstile, DataDome, and anti-bot systems.

| Feature / Metric | **Camoufox MCP** (`camoufox-playwright-mcp`) | **Standard Playwright MCP** (`@playwright/mcp`) |
|---|---|---|
| **Default Engine** | **Camoufox Anti-Detect Firefox** | Standard Chromium / Firefox |
| **`navigator.webdriver`** | **`false`** 🛡️ *(Masked)* | `true` 🚨 *(Detected)* |
| **Bot Detection (`bot.sannysoft.com`)** | **`PASSED`** ✅ | `FAILED` ❌ |
| **Generated Code Snippets** | **Python Playwright** (`await page.click(...)`) | JavaScript Playwright |
| **Unsafe Code Execution** | **Python Playwright Async** | JavaScript |
| **Hardware Fingerprinting** | Spoofed / Humanized | Raw Host Leak |
| **OS / Platform Spoofing** | Configurable (Windows / macOS / Linux) | Host Environment |
| **Tool Surface** | Full Official Specification | Full Official Specification |
| **Direct Execution** | `uvx camoufox-playwright-mcp` | `npx @playwright/mcp` |

---

## 🚀 Quickstart

### Run On-Demand with `uvx`

No installation required:

```bash
# Run stealth Camoufox browser in headless mode (recommended for AI agents)
uvx camoufox-playwright-mcp --headless

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

## 🥷 Stealth & Anti-Detect Configuration

When running with `--browser camoufox` (default), Camoufox applies advanced stealth configurations. You can customize anti-detect parameters via a JSON configuration file (`--config config.json`):

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

Full 1:1 match with official Playwright MCP specifications:

### Navigation & Interaction
* `browser_navigate`: Navigate to any URL with automatic wait-for-load.
* `browser_click`: Click elements using locators, coordinates, or semantic text.
* `browser_fill`: Fill input fields with anti-detection typing simulation.
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
