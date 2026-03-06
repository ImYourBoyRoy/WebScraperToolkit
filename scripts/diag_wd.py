# ./scripts/diag_wd.py
"""
Probe navigator.webdriver behavior in a local headed Chromium session.
Run: python ./scripts/diag_wd.py
Inputs: local Playwright browser runtime only.
Outputs: stdout lines showing navigator.webdriver and prototype webdriver presence.
Side effects: opens a visible browser and injects one init script on about:blank.
Operational notes: diagnostic-only check for webdriver suppression assumptions.
"""

from __future__ import annotations

from playwright.sync_api import sync_playwright


def run_webdriver_probe() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()

        context.add_init_script(
            """
            delete Object.getPrototypeOf(navigator).webdriver;
            """
        )

        page = context.new_page()
        page.goto("about:blank")

        webdriver_value = page.evaluate("navigator.webdriver")
        prototype_has_webdriver = page.evaluate(
            "'webdriver' in Object.getPrototypeOf(navigator)"
        )

        print(f"navigator.webdriver: {webdriver_value}")
        print(f"'webdriver' in prototype: {prototype_has_webdriver}")

        browser.close()


if __name__ == "__main__":
    run_webdriver_probe()
