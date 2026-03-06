# ./scripts/diag_stealth_bypass.py
"""
Test Stealth Bypass
===================

Tests the WebScraperToolkit stealth techniques against Google and DuckDuckGo.

Usage:
    python ./scripts/diag_stealth_bypass.py [--headed] [--provider google|ddg|both]

Inputs:
    CLI arguments:
        --headed: Run in headed mode to observe the browser behavior visually.
        --provider: Which provider to test (google, ddg, both).

Outputs:
    Exit code: 0 if all tests successful, 1 if any test blocked.
    Logs: Prints the status of the bypass attempt and the page title.
    Files: Writes `blocked_{provider}.html` to disk if blocked occurs.

Operation Notes:
    This script initializes a Playwright instance with the experimental SERP stealth
    profile techniques applied: randomized viewport, realistic hardware fingerprinting,
    Google consent cookies, and human-like micro-interactions.
"""

import argparse
import asyncio
import datetime
import random
import sys
from urllib.parse import quote_plus

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

COMMON_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1920, "height": 1080},
    {"width": 1280, "height": 800},
    {"width": 1600, "height": 900},
]

BASELINE_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--enable-webgl",
    "--window-size=1400,1000",
    "--no-sandbox",
    "--disable-infobars",
    "--disable-dev-shm-usage",
    "--ignore-certificate-errors",
]

# Experimental SERP profile launch arguments mimicking real Chrome defaults
EXPERIMENTAL_SERP_LAUNCH_ARGS = [
    "--disable-features=IsolateOrigins,site-per-process",
    "--disable-site-isolation-trials",
    "--disable-features=BlockInsecurePrivateNetworkRequests",
]


async def _perform_micro_interaction(page) -> None:
    """Apply tiny user-like interactions."""
    try:
        await page.mouse.move(
            random.randint(12, 140),
            random.randint(12, 100),
            steps=random.randint(3, 9),
        )
        await page.wait_for_timeout(random.uniform(120, 260))
    except Exception:
        pass


async def _solve_cloudflare_spatial(page) -> bool:
    """Basic fallback for Cloudflare just in case it's hit."""
    try:
        # Check if it's the checkbox frame
        challenge_frame = None
        for frame in page.frames:
            if "cf-chl-widget" in frame.name:
                challenge_frame = frame
                break

        if challenge_frame:
            await page.wait_for_timeout(random.uniform(1000, 2000))
            await _perform_micro_interaction(page)
            box = await challenge_frame.wait_for_selector(
                "input[type='checkbox']", timeout=5000
            )
            if box:
                await box.click()
                await page.wait_for_timeout(3000)
                return True
    except Exception as e:
        print(f"      [~] Cloudflare solve attempt error: {e}")
    return False


async def test_bypass(provider: str, headed: bool):
    async with async_playwright() as p:
        args = list(BASELINE_LAUNCH_ARGS) + EXPERIMENTAL_SERP_LAUNCH_ARGS

        # We don't specify user_agent. We let Playwright use its native Chromium version
        # to ensure the TLS fingerprint strictly matches the reported UA.
        browser = await p.chromium.launch(
            headless=not headed,
            args=args,
        )

        viewport = random.choice(COMMON_VIEWPORTS)
        context = await browser.new_context(
            viewport=viewport,
            screen=viewport,
            ignore_https_errors=True,
            java_script_enabled=True,
            locale="en-US",
            timezone_id="America/New_York",
        )

        # Scrub navigator properties explicitly, though playwright_stealth helps too
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Hardware init script for stealth
        await context.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
        """)

        # Consent cookies for Google to avoid popups and look like a returning user
        if provider in ("google", "both"):
            consent_date = datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y%m%d"
            )
            try:
                await context.add_cookies(
                    [
                        {
                            "name": "CONSENT",
                            "value": f"YES+cb.{consent_date}-04-p0.en+FX+{random.randint(100, 999)}",
                            "domain": ".google.com",
                            "path": "/",
                        },
                        {
                            "name": "SOCS",
                            "value": "CAISHAgBEhJnd3NfMjAyMzEwMTAtMF9SQzQaAmVuIAEaBgiA_LWoBg",
                            "domain": ".google.com",
                            "path": "/",
                        },
                    ]
                )
            except Exception as e:
                print(f"Warning: Failed to set cookies: {e}")

        targets = []
        if provider in ("google", "both"):
            q = quote_plus(
                "Amco Ranger Termite & Pest Solutions ceo email site:linkedin.com"
            )
            targets.append(
                ("Google", f"https://www.google.com/search?hl=en&num=15&q={q}")
            )
        if provider in ("ddg", "both"):
            q = quote_plus(
                "Amco Ranger Termite & Pest Solutions ceo email site:linkedin.com"
            )
            # DDG html fallback site
            targets.append(("DuckDuckGo", f"https://html.duckduckgo.com/html/?q={q}"))

        successes = 0
        for name, url in targets:
            print(f"\\n[*] Testing {name} bypass...")

            page = await context.new_page()
            # Apply playwright-stealth to the specific page before navigating
            stealth = Stealth()
            await stealth.apply_stealth_async(page)

            try:
                print(f"    Navigating to: {url}")
                response = await page.goto(
                    url, wait_until="domcontentloaded", timeout=45000
                )
                status = response.status if response else "Unknown"

                # Try micro interactions early
                await _perform_micro_interaction(page)

                # Check for cloudflare
                title = await page.title()
                if (
                    "just a moment" in title.lower()
                    or "attention required" in title.lower()
                ):
                    print("    [!] Cloudflare challenge hit. Attempting solve...")
                    await _solve_cloudflare_spatial(page)

                content = await page.content()
                title = await page.title()
                final_url = page.url

                print(f"    Status: {status}")
                print(f"    Title : {title}")
                print(f"    URL   : {final_url}")

                blocked = False
                if name == "Google":
                    if "google.com/sorry" in final_url or status in (403, 429):
                        blocked = True
                    elif any(
                        b in content.lower()
                        for b in [
                            "unusual traffic from your computer",
                            "our systems have detected unusual traffic",
                            "not a robot",
                        ]
                    ):
                        blocked = True
                elif name == "DuckDuckGo":
                    if any(
                        b in content.lower()
                        for b in [
                            "unfortunately, bots use duckduckgo too",
                            "anomaly-modal",
                            "cc=botnet",
                            "challenge-submit",
                        ]
                    ):
                        blocked = True

                if blocked:
                    print(f"    [!] BLOCKED by {name}")
                    filename = f"blocked_{name.lower()}.html"
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(content)
                    print(f"    Saved blocked page body to {filename}")
                else:
                    print(
                        f"    [+] SUCCESS bypassing {name} - Length of HTML: {len(content)}"
                    )
                    successes += 1

                await page.close()
            except Exception as e:
                print(f"    [X] Exception during test: {e}")

        await browser.close()

        if successes != len(targets):
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test stealth bypass for Google and DDG"
    )
    parser.add_argument("--headed", action="store_true", help="Run with headed browser")
    parser.add_argument(
        "--provider",
        choices=["google", "ddg", "both"],
        default="both",
        help="Provider to test",
    )
    args = parser.parse_args()

    asyncio.run(test_bypass(args.provider, args.headed))
