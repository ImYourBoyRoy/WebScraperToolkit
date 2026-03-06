# Support Matrix

## Python
- Supported: **3.10, 3.11, 3.12, 3.13**

## Operating systems
- Supported: **Windows, Linux, macOS**

## Browser channels
- Playwright managed: `chromium`, `firefox`, `webkit`
- Native fallback channels: `chrome`, `msedge`, `chromium`

## Mode support
- CLI scraping: ✅ supported on all supported OSes
- MCP server (stdio / streamable-http): ✅ supported
- Interactive challenge solve (OS input): ✅ requires headed mode and desktop session

## Known operational constraints
- OS-level PX solve requires visible desktop session and optional `web-scraper-toolkit[desktop]`.
- Headless mode intentionally blocks OS mouse takeover safeguards.
- Integration tests are intentionally separated and opt-in.

