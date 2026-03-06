# ./scripts/diag_headers.py
"""
Inspect outbound request headers emitted by headed Chrome for a baseline URL.
Run: python ./scripts/diag_headers.py
Inputs: hardcoded target URL (https://example.com) and local Playwright browser install.
Outputs: pretty-printed JSON headers captured from request events to stdout.
Side effects: launches a visible browser window and performs one network navigation.
Operational notes: diagnostic-only utility; intended for quick local header verification.
"""

from __future__ import annotations

import asyncio
import json

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, channel="chrome")
        context = await browser.new_context()
        page = await context.new_page()

        request_headers: dict[str, str] = {}

        async def on_request(request) -> None:
            nonlocal request_headers
            if "example.com" in request.url:
                request_headers = request.headers

        page.on("request", on_request)
        await page.goto("https://example.com")

        print("--- NATIVE HEADERS ---")
        print(json.dumps(request_headers, indent=2))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
