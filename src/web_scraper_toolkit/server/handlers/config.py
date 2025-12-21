# ./src/web_scraper_toolkit/server/tools/config.py
"""
Configuration Tools
===================

Global configuration management for MCP server tools.
Supports browser settings, stealth mode, and robots.txt compliance.
"""

from ...browser.config import BrowserConfig
from ...crawler.config import CrawlerConfig

# Global State (Shared across tools)
GLOBAL_BROWSER_CONFIG = BrowserConfig(headless=True)
GLOBAL_CRAWLER_CONFIG = CrawlerConfig()

# Stealth/Ethics Settings
GLOBAL_RESPECT_ROBOTS = True
GLOBAL_STEALTH_MODE = True


def update_browser_config(headless: bool = True) -> dict:
    """Updates the global browser configuration."""
    GLOBAL_BROWSER_CONFIG.headless = headless
    return {
        "headless": headless,
    }


def update_stealth_config(
    respect_robots: bool = True,
    stealth_mode: bool = True,
) -> dict:
    """
    Updates stealth and ethical crawling settings.

    Args:
        respect_robots: If True (default), respects robots.txt.
                       Set to False to ignore robots.txt restrictions.
        stealth_mode: If True (default), uses rotating realistic user-agents.

    Returns:
        dict with current settings.
    """
    global GLOBAL_RESPECT_ROBOTS, GLOBAL_STEALTH_MODE
    GLOBAL_RESPECT_ROBOTS = respect_robots
    GLOBAL_STEALTH_MODE = stealth_mode
    GLOBAL_CRAWLER_CONFIG.global_ignore_robots = not respect_robots

    return {
        "respect_robots": respect_robots,
        "stealth_mode": stealth_mode,
        "global_ignore_robots": GLOBAL_CRAWLER_CONFIG.global_ignore_robots,
    }


def get_current_config() -> dict:
    """Returns all current configuration settings."""
    return {
        "browser": {
            "headless": GLOBAL_BROWSER_CONFIG.headless,
            "browser_type": GLOBAL_BROWSER_CONFIG.browser_type,
            "timeout": GLOBAL_BROWSER_CONFIG.timeout,
        },
        "crawler": {
            "respect_robots": GLOBAL_RESPECT_ROBOTS,
            "stealth_mode": GLOBAL_STEALTH_MODE,
            "max_depth": GLOBAL_CRAWLER_CONFIG.default_max_depth,
            "max_pages": GLOBAL_CRAWLER_CONFIG.default_max_pages,
        },
    }
