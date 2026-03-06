# ./scripts/px_debug.py
"""
Inspect challenge-network behavior for an arbitrary target URL using headed Chrome.
Run: python ./scripts/px_debug.py [https://target-site.tld/path]
Inputs: optional positional URL argument; defaults to https://example.com/.
Outputs: console logs showing selected challenge-related response payloads and final PX cookie state.
Side effects: launches a visible browser window and performs network interception during the session.
Operational notes: testing-only script; intended for manual diagnostics of challenge API traffic.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")


async def log_px_response(response) -> None:
    url = response.url
    if (
        "/api/v2/collector" in url
        or "px/client" in url
        or "/xhr" in url
        or "captcha" in url
        or "11/" in url
    ):
        try:
            status = response.status
            if status == 200:
                text = await response.text()
                logging.info(f"PX API RESPONSE [{status}] {url[:100]}: {text[:300]}")
            else:
                logging.warning(f"PX API RESPONSE [{status}] {url[:100]}")
        except Exception:
            pass


async def main() -> None:
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False, channel="chrome", args=["--start-maximized"]
        )

        dummy = await browser.new_context()
        probe_page = await dummy.new_page()
        await probe_page.goto("about:blank")
        hw_probe = await probe_page.evaluate(
            """() => ({
            ua: navigator.userAgent,
            hw: navigator.hardwareConcurrency,
            mem: navigator.deviceMemory,
            touch: navigator.maxTouchPoints
        })"""
        )
        await dummy.close()

        context = await browser.new_context(
            no_viewport=True,
            locale="en-US",
            timezone_id="America/Denver",
            java_script_enabled=True,
            ignore_https_errors=True,
            has_touch=False,
        )

        async def _block_trackers(route) -> None:
            if (
                "bizographics" in route.request.url
                or "google-analytics" in route.request.url
            ):
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", _block_trackers)
        page = await context.new_page()

        stealth_js = f"""(() => {{
            try {{ delete Object.getPrototypeOf(navigator).webdriver; }} catch(e) {{}}
            Object.defineProperty(navigator, 'languages', {{ get: () => Object.freeze(['en-US', 'en']) }});
            Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => {hw_probe["hw"]} }});
            Object.defineProperty(navigator, 'deviceMemory', {{ get: () => {hw_probe["mem"]} }});
            if (!window.chrome) window.chrome = {{}};
            if (!window.chrome.runtime) window.chrome.runtime = {{ connect: () => {{}}, sendMessage: () => {{}} }};
            const origQuery = navigator.permissions.query.bind(navigator.permissions);
            Object.defineProperty(navigator.permissions, 'query', {{
                value: (p) => p && p.name === 'notifications' ? Promise.resolve({{ state: 'default' }}) : origQuery(p)
            }});
            Object.defineProperty(Notification, 'permission', {{ get: () => 'default' }});
        }})();"""
        await context.add_init_script(stealth_js)

        page.on(
            "response", lambda response: asyncio.create_task(log_px_response(response))
        )

        logging.info(f"Navigating to {target_url}")
        await page.goto(target_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(30000)

        cookies = await context.cookies()
        px_cookies = [cookie for cookie in cookies if cookie["name"].startswith("_px")]
        logging.info(f"Final PX cookies: {px_cookies}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
