# ./scripts/diag_observe_px.py
"""
Observe challenge-related DOM and request events for a target page in headed Chromium.
Run: python ./scripts/diag_observe_px.py [https://target-site.tld/path]
Inputs: optional positional URL argument; defaults to https://example.com/.
Outputs: console event stream for network requests and challenge button-state transitions.
Side effects: opens a visible persistent browser context and waits for manual interaction.
Operational notes: testing-only observer; does not persist site-specific routing decisions.
"""

from __future__ import annotations

import asyncio
import sys

from playwright.async_api import async_playwright


async def observe_px_events(target_url: str) -> None:
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="",
            headless=False,
            viewport={"width": 1366, "height": 768},
            screen={"width": 1366, "height": 768},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        page = context.pages[0]

        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        await page.add_init_script(
            """
            Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
            Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 0});
        """
        )

        print(f"[*] Navigating to target URL to observe challenge flow: {target_url}")
        page.on(
            "request",
            lambda request: (
                print(f"[NETWORK] {request.method} {request.url}")
                if "px-cloud" in request.url or "challenge" in request.url
                else None
            ),
        )

        await page.goto(target_url)

        print("[*] Please interact with the challenge manually in the opened browser.")
        print("[*] Monitoring DOM state transitions continuously...")

        last_state = ""
        last_html = ""

        while True:
            hold_element = None
            for frame in page.frames:
                for name in [
                    "Press & Hold",
                    "Human Challenge completed,",
                    "Verify you are human",
                ]:
                    locator = frame.get_by_role("button", name=name)
                    if await locator.count() > 0:
                        hold_element = locator
                        break
                if hold_element:
                    break

            if (
                hold_element
                and await hold_element.count() > 0
                and await hold_element.first.is_visible()
            ):
                text = await hold_element.first.inner_text()
                aria_label = await hold_element.first.get_attribute("aria-label") or ""
                current_state = f"{text} | {aria_label}"

                if current_state != last_state:
                    print(f"\n[STATE SHIFT] Button state changed to: {current_state}")
                    last_state = current_state

                button_html = await hold_element.first.evaluate("el => el.outerHTML")
                if button_html != last_html:
                    print("[DOM CHANGE] Updated challenge button HTML:")
                    print(button_html[:800])
                    last_html = button_html

            await asyncio.sleep(0.5)


def main() -> None:
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com/"
    asyncio.run(observe_px_events(target_url))


if __name__ == "__main__":
    main()
