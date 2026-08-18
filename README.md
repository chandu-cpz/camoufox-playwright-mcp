# Camoufox Playwright MCP

[![PyPI version](https://img.shields.io/pypi/v/camoufox-playwright-mcp.svg)](https://pypi.org/project/camoufox-playwright-mcp/)
[![Python Version](https://img.shields.io/pypi/pyversions/camoufox-playwright-mcp.svg)](https://pypi.org/project/camoufox-playwright-mcp/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

An official-parity Playwright Model Context Protocol (MCP) server supercharged with **Camoufox** — the stealth, anti-detect browser engine designed to bypass anti-bot systems, Cloudflare Turnstile, DataDome, and advanced browser fingerprinting out of the box.

---

## Highlights

- 🥷 **Stealth by Default**: Powered by Camoufox's custom anti-detect browser engine with hardware spoofing, humanized cursor movements, and GeoIP alignment.
- 🎭 **100% Official Playwright MCP Parity**: Full tool parity with the official TypeScript Playwright MCP (`browser_navigate`, `browser_click`, `browser_fill`, `browser_snapshot`, `browser_take_screenshot`, `browser_evaluate`, etc.).
- 🔄 **Dual Engine Flexibility**: Run with stealth `camoufox` by default, or seamlessly switch to standard Playwright browsers (`chromium`, `chrome`, `firefox`, `webkit`) or custom CDP endpoints.
- ⚡ **Zero Install via `uvx`**: Run instantly in Claude Desktop, Cursor, Cline, Windsurf, or any MCP client without manual setup.

---

## Quickstart

### 1. Run On-The-Fly with `uvx`

No prior installation needed:

```bash
# Run stealth Camoufox browser in headless mode (recommended for AI agents)
uvx camoufox-playwright-mcp --headless

# Or run with standard Chrome
uvx camoufox-playwright-mcp --browser chrome
```

---

### 2. Client Configurations

#### Claude Desktop

Add this to your `claude_desktop_config.json`:

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

#### Cursor (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "camoufox": {
      "command": "uvx",
      "args": ["camoufox-playwright-mcp", "--headless"]
    }
  }
}
```

#### Windsurf / Cline / OpenCode / Zed

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

## Installation

You can also install `camoufox-playwright-mcp` into your virtual environment:

### Using `uv`
```bash
uv add camoufox-playwright-mcp
```

### Using `pip`
```bash
pip install camoufox-playwright-mcp
```

### Installing Browser Binaries
Fetch the Camoufox browser binary:
```bash
camoufox-playwright-mcp install-browser
```

To install standard Playwright browsers as well:
```bash
camoufox-playwright-mcp install-browser chromium firefox webkit
# or install all
camoufox-playwright-mcp install-browser all
```

---

## CLI Reference

```
usage: camoufox-playwright-mcp [-h] [--browser BROWSER] [--headless] [--isolated]
                               [--user-data-dir USER_DATA_DIR] [--proxy-server PROXY_SERVER]
                               [--cdp-endpoint CDP_ENDPOINT] [--port PORT] ...
```

### Common Flags

| Option | Description |
|---|---|
| `--browser` | Browser to use: `camoufox` (default), `chrome`, `chromium`, `firefox`, `webkit`. |
| `--headless` | Run browser in headless mode. |
| `--isolated` | Create fresh, temporary browser context instead of persistent profile. |
| `--user-data-dir` | Custom directory path for browser profile storage. |
| `--proxy-server` | Proxy server URL (e.g. `http://user:pass@proxy.example.com:8080`). |
| `--proxy-bypass` | Comma-separated list of domains to bypass the proxy. |
| `--timeout-action` | Action timeout in milliseconds (default: `5000`). |
| `--timeout-navigation` | Navigation timeout in milliseconds (default: `60000`). |
| `--output-dir` | Directory for saved snapshots, screenshots, and logs. |
| `--output-mode` | Return artifacts inline or by file reference (`file` or `stdout`). |
| `--port` | Port to listen on for HTTP/SSE transport (runs stdio transport if omitted). |

### Commands

- `camoufox-playwright-mcp install-browser`: Downloads Camoufox and/or Playwright browser binaries.

---

## Camoufox Stealth & Anti-Detect Options

When running with `--browser camoufox` (default), Camoufox applies advanced stealth configurations. You can provide deeper configurations via a JSON config file (`--config config.json`):

```json
{
  "browser": {
    "provider": "camoufox",
    "camoufoxOptions": {
      "geoip": true,
      "humanize": true,
      "os": "windows",
      "block_images": false
    }
  }
}
```

---

## Environment Variables

All CLI flags can be configured via environment variables:

| Variable | Description |
|---|---|
| `CAMOUFOX_MCP_BROWSER` | Default browser (`camoufox`, `chrome`, `chromium`, etc.) |
| `CAMOUFOX_MCP_HEADLESS` | Set to `true` or `1` for headless mode |
| `CAMOUFOX_MCP_ISOLATED` | Set to `true` to use isolated contexts |
| `CAMOUFOX_MCP_PROXY_SERVER` | Proxy server URL |
| `CAMOUFOX_MCP_OUTPUT_DIR` | Output directory for artifacts |
| `CAMOUFOX_MCP_CONFIG` | Path to JSON/INI configuration file |

*(Note: `PLAYWRIGHT_MCP_*` variables are also supported for backward compatibility).*

---

## Available MCP Tools

Full 1:1 match with official Playwright MCP specifications:

- `browser_navigate`: Navigate to a specified URL.
- `browser_click`: Click on elements using locators, coordinates, or text.
- `browser_fill`: Fill input fields with anti-detection keystrokes.
- `browser_snapshot`: Capture full accessibility and semantic tree snapshots.
- `browser_take_screenshot`: Capture full-page or element screenshots.
- `browser_evaluate`: Safely evaluate JavaScript within the page context.
- `browser_hover`, `browser_press_key`, `browser_type`: Mouse & keyboard interactions.
- `browser_tabs`: Manage multiple browser tabs and windows.
- `browser_cookies`: Get, set, and clear cookies.
- `browser_network`: Manage routes and network interception.

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
