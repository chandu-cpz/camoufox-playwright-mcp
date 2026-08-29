# Changelog

All notable changes to `camoufox-playwright-mcp` are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.5] - 2026-08-26

### Changed
- Repositioned package around the anti-detect value proposition.
  Tagline, project description, Highlights, and the "What this is" section
  in the README now lead with what the tool does (Playwright MCP tools on
  a fingerprint-resistant browser) instead of leading with provenance
  ("unofficial port of the official one"). The affiliation clarification
  with Microsoft and the Playwright team is kept as a clarity line.
- Updated `pyproject.toml` short description to match the new positioning.
  This is the line that shows up in PyPI search results.

### Added
- `CHANGELOG.md` to track release notes going forward.

## [0.1.4] - 2026-08-21

### Fixed
- Sanitize error output to strip tracebacks and absolute paths; prevents
  `/home/...` leaks on `NS_ERROR_UNKNOWN_HOST` (`file://` and invalid host).
- Validation middleware in the MCP server catches FastMCP/pydantic
  validation errors and returns clean `Invalid arguments for tool "X":`
  messages matching official formatting instead of raw pydantic tracebacks.
- Tab layer: `Error:` prefix added to "Ref not found" to match the official
  server's error format.
- `go_back` / `go_forward` use `domcontentloaded` with abort handling;
  engine limitation documented; history pollution is upstream Camoufox.

### Verified
- 24/24 tool parity with the official Playwright MCP, snapshot/codegen
  diffs only in expected language/UA, identical `isError` semantics.

## [0.1.3] - 2026-08-21

### Added
- Honest positioning in README: the port relationship to the official
  Microsoft `@playwright/mcp` is described accurately without overselling.
- `SECURITY.md` covering credential handling, profile isolation, and the
  extension relay.
- GitHub issue templates (`bug_report.yml`, `config.yml`).

### Fixed
- Error de-duplication in tool responses.

## [0.1.2] - 2026-08-18

### Fixed
- WebStorage tool regressions introduced in 0.1.1.
- CLI flag precedence (`--browser` and friends no longer collide with
  config-file values).
- macOS-specific `/proc` guard for the profile-isolation path.

### Changed
- README rewritten with explicit Quickstart, Client Configuration, and
  Tool Reference sections; install instructions now lead with `uvx`.

## [0.1.1] - 2026-08-18

### Fixed
- Camoufox persistent profile directory namespace isolated from standard
  Firefox, preventing shared-profile collisions when both are installed.

## [0.1.0] - 2026-08-18

### Added
- Initial public release.
- 24 MCP tools with full parity against the official `@playwright/mcp`
  tool contract.
- Camoufox as the default browser engine, with `chromium`, `chrome`,
  `firefox`, and `webkit` available as fallbacks.
- `stdio` and Streamable HTTP transports.
- Persistent and isolated browser context modes.
- CDP endpoint and Playwright browser extension relay support.
- INI and JSON configuration formats.
- Python-native code generation in `browser_*` outputs.
- Apache 2.0 license.
