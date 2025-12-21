# ./src/web_scraper_toolkit/core/automation/forms.py
"""
Form Automation
===============

Enables automated form filling, login handling, and session persistence.
Critical for authenticated scraping and interactive web automation.

Usage:
    result = await fill_form(
        url="https://example.com/login",
        fields={"#username": "user", "#password": "pass"},
        submit_selector="button[type=submit]",
        save_session=True
    )

Key Features:
    - Selector-based field filling
    - Automatic form submission
    - Session persistence for logins
    - Screenshot on completion (optional)
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


async def fill_form(
    url: str,
    fields: Dict[str, str],
    submit_selector: Optional[str] = None,
    wait_after_submit: int = 3000,
    save_session: bool = True,
    session_name: str = "default",
    screenshot_path: Optional[str] = None,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Fill and submit a web form.

    Args:
        url: URL of the page containing the form
        fields: Dict mapping CSS selectors to values
                e.g. {"#username": "user", "#password": "pass"}
        submit_selector: CSS selector for submit button (optional)
        wait_after_submit: Milliseconds to wait after submission
        save_session: If True, save session state for future requests
        session_name: Name for saved session
        screenshot_path: Optional path to save screenshot after submit
        headless: Run browser in headless mode

    Returns:
        Dict with success status, final URL, and session info.
    """
    try:
        from ...browser.playwright_handler import PlaywrightManager
        from ...browser.config import BrowserConfig
        from ..state.session import get_session_manager

        session_mgr = get_session_manager()

        # Configure browser
        config = BrowserConfig(headless=headless)

        async with PlaywrightManager(config=config) as manager:
            # Load existing session if available
            storage_state = session_mgr.get_storage_state_path(session_name)

            context_kwargs = {}
            if storage_state:
                context_kwargs["storage_state"] = storage_state

            context = await manager.browser.new_context(**context_kwargs)
            page = await context.new_page()

            try:
                # Navigate to form page
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle", timeout=10000)

                # Fill each field
                filled_fields = []
                for selector, value in fields.items():
                    try:
                        # Wait for field to be visible
                        await page.wait_for_selector(selector, timeout=5000)

                        # Clear existing value and fill
                        await page.fill(selector, "")
                        await page.fill(selector, value)
                        filled_fields.append(selector)
                        logger.debug(f"Filled field: {selector}")
                    except Exception as e:
                        logger.warning(f"Could not fill {selector}: {e}")

                # Submit form if selector provided
                submitted = False
                if submit_selector:
                    try:
                        await page.click(submit_selector)
                        submitted = True
                        await page.wait_for_timeout(wait_after_submit)
                        await page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception as e:
                        logger.warning(f"Submit failed: {e}")

                # Get final URL after submission
                final_url = page.url

                # Take screenshot if requested
                if screenshot_path:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=screenshot_path, full_page=True)

                # Save session state
                session_saved = False
                if save_session:
                    session_saved = await session_mgr.save_state(context, session_name)

                return {
                    "success": True,
                    "url": url,
                    "final_url": final_url,
                    "fields_filled": filled_fields,
                    "submitted": submitted,
                    "session_saved": session_saved,
                    "session_name": session_name if session_saved else None,
                    "screenshot": screenshot_path if screenshot_path else None,
                }

            finally:
                await context.close()

    except Exception as e:
        logger.error(f"Form fill failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "url": url,
        }


async def extract_tables(
    url: str,
    table_selector: str = "table",
    include_headers: bool = True,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Extract structured table data from webpage.

    Args:
        url: URL containing tables
        table_selector: CSS selector for tables (default: "table")
        include_headers: Include table headers in output
        headless: Run browser in headless mode

    Returns:
        Dict with list of tables, each containing headers and rows.
    """
    try:
        from ...browser.playwright_handler import PlaywrightManager
        from ...browser.config import BrowserConfig

        config = BrowserConfig(headless=headless)

        async with PlaywrightManager(config=config) as manager:
            context = await manager.browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle", timeout=15000)

                # Extract all tables
                tables_data = await page.evaluate(
                    """
                    (selector) => {
                        const tables = document.querySelectorAll(selector);
                        return Array.from(tables).map(table => {
                            const headers = Array.from(table.querySelectorAll('thead th, thead td, tr:first-child th'))
                                .map(th => th.textContent.trim());
                            
                            const rows = Array.from(table.querySelectorAll('tbody tr, tr'))
                                .slice(headers.length > 0 ? 0 : 1)  // Skip header row if extracted
                                .map(tr => Array.from(tr.querySelectorAll('td, th'))
                                    .map(td => td.textContent.trim())
                                );
                            
                            return { headers, rows };
                        });
                    }
                    """,
                    table_selector,
                )

                return {
                    "success": True,
                    "url": url,
                    "tables": tables_data,
                    "count": len(tables_data),
                }

            finally:
                await context.close()

    except Exception as e:
        logger.error(f"Table extraction failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "url": url,
            "tables": [],
            "count": 0,
        }


async def click_element(
    url: str,
    selector: str,
    wait_after_click: int = 2000,
    screenshot_path: Optional[str] = None,
    headless: bool = True,
) -> Dict[str, Any]:
    """
    Navigate to URL and click an element.

    Useful for triggering JavaScript actions, expanding sections, etc.

    Args:
        url: Page URL
        selector: CSS selector for element to click
        wait_after_click: Milliseconds to wait after clicking
        screenshot_path: Optional screenshot after click
        headless: Run in headless mode

    Returns:
        Dict with click status and final page state.
    """
    try:
        from ...browser.playwright_handler import PlaywrightManager
        from ...browser.config import BrowserConfig

        config = BrowserConfig(headless=headless)

        async with PlaywrightManager(config=config) as manager:
            context = await manager.browser.new_context()
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle", timeout=10000)

                # Wait for and click element
                await page.wait_for_selector(selector, timeout=5000)
                await page.click(selector)
                await page.wait_for_timeout(wait_after_click)

                final_url = page.url

                if screenshot_path:
                    Path(screenshot_path).parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=screenshot_path, full_page=True)

                return {
                    "success": True,
                    "clicked": selector,
                    "final_url": final_url,
                    "screenshot": screenshot_path,
                }

            finally:
                await context.close()

    except Exception as e:
        logger.error(f"Click failed: {e}")
        return {
            "success": False,
            "error": str(e),
        }
