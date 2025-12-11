# ./src/web_scraper_toolkit/core/diagnostics.py
"""
Diagnostics Module
==================

Provides system self-checks to ensure the environment is correctly configured.
Checks Playwright installation, browser binaries, and network connectivity.

Usage:
    print_diagnostics()

Outputs:
    - Printed report of system status to stdout.
"""

import asyncio
import logging
import sys
from typing import Dict, Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def verify_environment() -> Dict[str, Any]:
    """
    Checks the scraping environment for necessary dependencies and functionality.

    Returns:
        Dict containing status of:
        - python_version
        - playwright_installed
        - browser_launch_successful
        - browsers_found
    """
    report = {
        "python_version": sys.version,
        "playwright_installed": False,
        "browser_launch_successful": False,
        "browsers_found": [],
        "errors": [],
    }

    # 1. Check Playwright Import
    try:
        from importlib.util import find_spec
        if find_spec("playwright"):
             report["playwright_installed"] = True
        else:
             report["errors"].append("Playwright package not found.")
    except ImportError:
        report["errors"].append("Playwright package not installed.")
        return report

    # 2. Check Browsers
    try:
        async with async_playwright() as p:
            # Try launching Chromium
            try:
                browser = await p.chromium.launch(headless=True)
                report["browsers_found"].append("chromium")
                report["browser_launch_successful"] = True
                await browser.close()
            except Exception as e:
                report["errors"].append(f"Chromium launch failed: {e}")

            # Try launching Firefox (optional but good to know)
            try:
                browser = await p.firefox.launch(headless=True)
                report["browsers_found"].append("firefox")
                await browser.close()
            except Exception:
                pass  # Firefox might not be installed, that's okay

    except Exception as e:
        report["errors"].append(f"Playwright runtime error: {e}")

    return report


def print_diagnostics():
    """Runs the verification and prints a human-readable report."""
    print("Running WebScraperToolkit Diagnostics...")
    try:
        results = asyncio.run(verify_environment())

        print(f"\nPython Version: {results['python_version'].split()[0]}")
        print(
            f"Playwright Installed: {'✅' if results['playwright_installed'] else '❌'}"
        )

        if results["playwright_installed"]:
            if results["browser_launch_successful"]:
                print("Browser Launch: ✅ (Chromium)")
            else:
                print("Browser Launch: ❌")

            print(f"Browsers Detected: {', '.join(results['browsers_found'])}")

        if results["errors"]:
            print("\n⚠️ Issues Found:")
            for err in results["errors"]:
                print(f"  - {err}")

            if "Executable doesn't exist" in str(results["errors"]):
                print(
                    "\nSuggestion: Run `playwright install` to download necessary browsers."
                )
    except Exception as e:
        print(f"Diagnostics failed to run: {e}")
