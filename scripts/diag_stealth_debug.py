# ./scripts/diag_stealth_debug.py
"""
Run a focused stealth-debug navigation flow against httpbin and Google Search.
Run: python ./scripts/diag_stealth_debug.py
Inputs: local Playwright runtime and optional playwright-stealth package.
Outputs: stdout logs for request headers, final status, title, and block classification.
Side effects: opens a headless Chromium session and performs outbound web requests.
Operational notes: diagnostic script for manual troubleshooting, not deterministic CI.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def run_search_probe() -> None:
    async with async_playwright() as playwright:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--disable-gpu",
        ]

        # HEADLESS=TRUE, simulating our exact scraper setup
        browser = await playwright.chromium.launch(
            headless=True, args=args, ignore_default_args=["--enable-automation"]
        )

        # NO USER AGENT SET - allowing Native Playwright UA
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
        )

        page = await context.new_page()

        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        print("[*] Checking headers via httpbin...")
        await page.goto("https://httpbin.org/headers")
        print(await page.inner_text("body"))

        print("\n[*] Navigating to Google Search...")
        url = "https://www.google.com/search?hl=en&num=15&q=Amco+Ranger+Termite+%26+Pest+Solutions+ceo+email+site%3Alinkedin.com"

        response = await page.goto(url, wait_until="domcontentloaded")

        print(f"Status: {response.status if response else 'Unknown'}")
        title = await page.title()
        print(f"Title : {title}")
        print(f"URL   : {page.url}")

        if "sorry/index" in page.url:
            print("[!] Google Blocked the request (Redirected to /sorry/)")
        elif "Google Search" in title or "LinkedIn" in title:
            print("[+] Google Request Successful!")
        else:
            print(f"[?] Unknown outcome. Title was: {title}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_search_probe())
