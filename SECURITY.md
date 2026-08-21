# Security policy

This is an unofficial, single-maintainer Python port of Microsoft's Playwright MCP server, with [Camoufox](https://github.com/daijro/camoufox) as the default browser. It is not affiliated with Microsoft or the Playwright team.

## Reporting a vulnerability

Use [GitHub's private vulnerability reporting](https://github.com/chandu-cpz/camoufox-playwright-mcp/security/advisories/new). Do not open a public issue for anything that could expose users, such as credential handling, profile isolation, or the extension relay.

There is no fixed disclosure timeline. This is a side project; I respond when I can.

## Do not paste secrets in issues

This server drives real browser sessions. When filing any issue:

- Never paste cookies, storage state files, or `browser_storage_state` output.
- Never paste session tokens, API keys, or URLs containing signed-in session identifiers.
- Scrub screenshots and logs too. `browser_snapshot` output can include the text of logged-in pages.

If you already posted something sensitive, rotate the credential first, then edit or delete the post.

## Known sharp edges

These are design decisions, not vulnerabilities, but you should know about them:

- `browser_evaluate` runs arbitrary JavaScript in the page, and `browser_run_code_unsafe` runs arbitrary Python against the page. That is the point of the tools. Navigating to untrusted pages while these tools are exposed to your agent is a risk you accept.
- The server trusts its MCP client. It does not defend against a malicious client, since the client already runs with your privileges.
- Persistent profiles (the default) keep logins and cookies on disk under your cache directory. Treat that directory like a real browser profile.

## Dependency vulnerabilities

For a vulnerable dependency, a normal PR bumping the pin in `pyproject.toml` / `uv.lock` is the fastest fix and is very welcome.
