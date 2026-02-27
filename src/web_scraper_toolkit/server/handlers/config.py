# ./src/web_scraper_toolkit/server/handlers/config.py
"""
Implement shared MCP runtime configuration handlers.
Used by management MCP tools to mutate/read browser and crawl behavior settings.
Run: Imported by MCP tool registration; not executed directly.
Inputs: Headless and stealth/robots flags.
Outputs: Updated configuration dictionaries for MCP envelopes.
Side effects: Mutates module-level runtime config shared by active MCP process.
Operational notes: Globals keep current behavior for backward compatibility.
"""

from ...browser.config import BrowserConfig
from ...core.runtime import RuntimeSettings, load_runtime_settings
from ...crawler.config import CrawlerConfig

# Global State (Shared across tools)
GLOBAL_BROWSER_CONFIG = BrowserConfig(headless=True)
GLOBAL_CRAWLER_CONFIG = CrawlerConfig()
GLOBAL_RUNTIME_SETTINGS: RuntimeSettings = load_runtime_settings()

# Stealth/Ethics Settings
GLOBAL_RESPECT_ROBOTS = True
GLOBAL_STEALTH_MODE = True


def _merge_nested(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _merge_nested(target[key], value)
            continue
        target[key] = value


def update_browser_config(
    headless: bool = True,
    browser_type: str | None = None,
    timeout_ms: int | None = None,
) -> dict:
    """Updates the global browser configuration."""
    GLOBAL_BROWSER_CONFIG.headless = headless
    if browser_type:
        GLOBAL_BROWSER_CONFIG.browser_type = browser_type
    if timeout_ms is not None and timeout_ms > 0:
        GLOBAL_BROWSER_CONFIG.timeout = timeout_ms
    return {
        "headless": headless,
        "browser_type": GLOBAL_BROWSER_CONFIG.browser_type,
        "timeout_ms": GLOBAL_BROWSER_CONFIG.timeout,
    }


def refresh_runtime_config(
    config_json_path: str | None = None,
    local_cfg_path: str | None = None,
) -> dict:
    """Reload runtime settings from config sources."""
    global GLOBAL_RUNTIME_SETTINGS
    GLOBAL_RUNTIME_SETTINGS = load_runtime_settings(
        config_json_path=config_json_path,
        local_cfg_path=local_cfg_path,
    )
    return GLOBAL_RUNTIME_SETTINGS.as_dict()


def get_runtime_config() -> RuntimeSettings:
    """Get shared runtime settings object."""
    return GLOBAL_RUNTIME_SETTINGS


def update_runtime_overrides(overrides: dict) -> dict:
    """
    Apply runtime overrides on top of existing settings.

    This enables dynamic tuning via MCP calls without editing files.
    """
    global GLOBAL_RUNTIME_SETTINGS

    if not isinstance(overrides, dict):
        return GLOBAL_RUNTIME_SETTINGS.as_dict()

    merged = {"runtime": GLOBAL_RUNTIME_SETTINGS.as_dict()}
    runtime_updates = overrides.get("runtime", overrides)
    if isinstance(runtime_updates, dict):
        _merge_nested(merged["runtime"], runtime_updates)

    GLOBAL_RUNTIME_SETTINGS = load_runtime_settings(overrides=merged)
    return GLOBAL_RUNTIME_SETTINGS.as_dict()


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
        "runtime": GLOBAL_RUNTIME_SETTINGS.as_dict(),
    }
