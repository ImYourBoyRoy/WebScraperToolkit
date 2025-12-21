# ./src/web_scraper_toolkit/browser/config.py
"""
Browser Configuration
=====================

Configuration for Playwright-based scraping.

Note: We deliberately do NOT set a custom user_agent for Playwright contexts.
Leaving it native allows Chromium to report its version (e.g. Chrome/131),
which matches the TLS fingerprint and helps pass Cloudflare challenges.
"""

from dataclasses import dataclass, asdict


@dataclass
class BrowserConfig:
    headless: bool = True
    browser_type: str = "chromium"
    viewport_width: int = 1280
    viewport_height: int = 800
    timeout: int = 30000
    # Note: No user_agent field - Playwright uses native UA for stealth

    def to_dict(self) -> dict:
        return asdict(self)
