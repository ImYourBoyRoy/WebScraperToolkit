# ./scripts/diag_simple_stealth.py
"""
Simple Stealth Test
===================

You were completely right: the block is a fingerprinting issue, NOT an IP rate limit.

THE BREAKTHROUGH DISCOVERY:
The `playwright_stealth` library is actually CAUSING the Google block.
Version 2.0.0 injects outdated JavaScript shims (like older mocked plugin arrays) that
Google's advanced reCAPTCHA Enterprise systems specifically flag as bot behavior.

Furthermore, Playwright natively injects "HeadlessChrome" into both the `User-Agent`
and `Sec-Ch-Ua` HTTP headers when running in headless mode, which `playwright_stealth`
does NOT patch (it only patches JS objects).

This script demonstrates the working bypass without `playwright_stealth`. It dynamically
strips "HeadlessChrome" from the HTTP headers, preserves the exact Chromium version for
TLS matching, and scrubs `navigator.webdriver`.
"""

import asyncio
import re
from playwright.async_api import async_playwright


async def test_search():
    async with async_playwright() as p:
        # Crucial args to hide Playwright's automation tags
        args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        browser = await p.chromium.launch(
            headless=True, args=args, ignore_default_args=["--enable-automation"]
        )

        # 1. Get native UA to extract the exact Chromium version
        dummy_context = await browser.new_context()
        dummy_page = await dummy_context.new_page()
        native_ua = await dummy_page.evaluate("navigator.userAgent")
        await dummy_context.close()

        # 2. Strip HeadlessChrome from UA to prevent instant HTTP header flagging
        clean_ua = native_ua.replace("HeadlessChrome", "Chrome")

        # 3. Extract major version for sec-ch-ua (e.g., "141")
        match = re.search(r"Chrome/(\d+)\.", clean_ua)
        major_version = match.group(1) if match else "131"

        # 4. Construct clean sec-ch-ua headers dynamically
        extra_headers = {
            "Sec-Ch-Ua": f'"Google Chrome";v="{major_version}", "Not=A?Brand";v="8", "Chromium";v="{major_version}"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Accept-Language": "en-US,en;q=0.9",  # Standard accept language
        }

        # 5. Create context with patched UA and Client Hints
        context = await browser.new_context(
            user_agent=clean_ua,
            viewport={"width": 1920, "height": 1080},
            extra_http_headers=extra_headers,
            locale="en-US",
            timezone_id="America/New_York",
            java_script_enabled=True,
        )

        page = await context.new_page()

        # 6. Scrub webdriver (the ONLY JS patch we actually need)
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        print("[*] Navigating to Google Search...")
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
    asyncio.run(test_search())
