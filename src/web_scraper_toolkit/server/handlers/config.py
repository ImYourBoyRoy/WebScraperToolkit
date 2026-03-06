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

from typing import Any, Mapping

from ...browser.config import BrowserConfig
from ...browser.host_profiles import HostProfileStore, normalize_host
from ...core.runtime import RuntimeSettings, load_runtime_settings
from ...crawler.config import CrawlerConfig

# Global State (Shared across tools)
GLOBAL_BROWSER_CONFIG = BrowserConfig(headless=True)
GLOBAL_CRAWLER_CONFIG = CrawlerConfig()
GLOBAL_RUNTIME_SETTINGS: RuntimeSettings = load_runtime_settings()
GLOBAL_HOST_PROFILE_STORE: HostProfileStore | None = None
GLOBAL_HOST_PROFILE_STORE_SIG: tuple[str, int, str] | None = None

# Stealth/Ethics Settings
GLOBAL_RESPECT_ROBOTS = True
GLOBAL_STEALTH_MODE = True


def _merge_nested(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            _merge_nested(target[key], value)
            continue
        target[key] = value


def _current_host_profile_sig(config: BrowserConfig) -> tuple[str, int, str]:
    return (
        str(config.host_profiles_path),
        int(config.host_learning_promotion_threshold),
        str(config.host_learning_apply_mode),
    )


def get_host_profile_store() -> HostProfileStore:
    """Return shared host profile store synced to the current browser config."""
    global GLOBAL_HOST_PROFILE_STORE, GLOBAL_HOST_PROFILE_STORE_SIG
    sig = _current_host_profile_sig(GLOBAL_BROWSER_CONFIG)
    if GLOBAL_HOST_PROFILE_STORE is None or GLOBAL_HOST_PROFILE_STORE_SIG != sig:
        try:
            GLOBAL_HOST_PROFILE_STORE = HostProfileStore(
                path=GLOBAL_BROWSER_CONFIG.host_profiles_path,
                promotion_threshold=GLOBAL_BROWSER_CONFIG.host_learning_promotion_threshold,
                apply_mode=GLOBAL_BROWSER_CONFIG.host_learning_apply_mode,
                auto_create=True,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Unable to initialize host profile store at "
                f"'{GLOBAL_BROWSER_CONFIG.host_profiles_path}': {exc}"
            ) from exc
        GLOBAL_HOST_PROFILE_STORE_SIG = sig
    return GLOBAL_HOST_PROFILE_STORE


def update_browser_config(
    headless: bool | None = None,
    browser_type: str | None = None,
    timeout_ms: int | None = None,
    native_fallback_policy: str | None = None,
    native_browser_channels: str | list[str] | tuple[str, ...] | None = None,
    native_browser_headless: bool | None = None,
    native_context_mode: str | None = None,
    native_profile_dir: str | None = None,
    interactive_channel: str | None = None,
    interactive_context_mode: str | None = None,
    interactive_profile_dir: str | None = None,
    host_profiles_enabled: bool | None = None,
    host_profiles_path: str | None = None,
    host_profiles_read_only: bool | None = None,
    host_learning_enabled: bool | None = None,
    host_learning_apply_mode: str | None = None,
    host_learning_promotion_threshold: int | None = None,
) -> dict:
    """Updates the global browser configuration."""
    global GLOBAL_BROWSER_CONFIG
    merged = GLOBAL_BROWSER_CONFIG.to_dict()

    if headless is not None:
        merged["headless"] = bool(headless)
    if browser_type:
        merged["browser_type"] = browser_type
    if timeout_ms is not None and timeout_ms > 0:
        merged["timeout"] = int(timeout_ms)

    if native_fallback_policy is not None:
        merged["native_fallback_policy"] = native_fallback_policy
    if native_browser_channels is not None:
        merged["native_browser_channels"] = native_browser_channels
    if native_browser_headless is not None:
        merged["native_browser_headless"] = bool(native_browser_headless)
    if native_context_mode is not None:
        merged["native_context_mode"] = native_context_mode
    if native_profile_dir is not None:
        merged["native_profile_dir"] = str(native_profile_dir)
    if interactive_channel is not None:
        merged["interactive_channel"] = interactive_channel
    if interactive_context_mode is not None:
        merged["interactive_context_mode"] = interactive_context_mode
    if interactive_profile_dir is not None:
        merged["interactive_profile_dir"] = str(interactive_profile_dir)
    if host_profiles_enabled is not None:
        merged["host_profiles_enabled"] = bool(host_profiles_enabled)
    if host_profiles_path is not None:
        merged["host_profiles_path"] = str(host_profiles_path)
    if host_profiles_read_only is not None:
        merged["host_profiles_read_only"] = bool(host_profiles_read_only)
    if host_learning_enabled is not None:
        merged["host_learning_enabled"] = bool(host_learning_enabled)
    if host_learning_apply_mode is not None:
        merged["host_learning_apply_mode"] = str(host_learning_apply_mode)
    if (
        host_learning_promotion_threshold is not None
        and host_learning_promotion_threshold > 0
    ):
        merged["host_learning_promotion_threshold"] = int(
            host_learning_promotion_threshold
        )

    GLOBAL_BROWSER_CONFIG = BrowserConfig.from_dict(merged)
    if GLOBAL_BROWSER_CONFIG.host_profiles_enabled:
        get_host_profile_store()
    else:
        global GLOBAL_HOST_PROFILE_STORE, GLOBAL_HOST_PROFILE_STORE_SIG
        GLOBAL_HOST_PROFILE_STORE = None
        GLOBAL_HOST_PROFILE_STORE_SIG = None
    result = GLOBAL_BROWSER_CONFIG.to_dict()
    result["timeout_ms"] = GLOBAL_BROWSER_CONFIG.timeout
    return result


def get_browser_config() -> BrowserConfig:
    """Return a defensive copy of current global browser config."""
    return BrowserConfig.from_dict(GLOBAL_BROWSER_CONFIG.to_dict())


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


def get_host_profiles(host: str | None = None) -> dict:
    """Return host profile store snapshot (all hosts or a single host)."""
    store = get_host_profile_store()
    if host:
        return store.export_profiles(host=host)
    return store.export_profiles()


def clear_host_profile(host: str) -> dict:
    """Delete one host profile record."""
    store = get_host_profile_store()
    host_key = normalize_host(host)
    removed = store.clear_host_profile(host_key)
    return {
        "host": host_key,
        "removed": removed,
    }


def set_host_profile(host: str, profile_payload: Mapping[str, Any]) -> dict:
    """Set/replace active routing profile for a host (manual admin override)."""
    store = get_host_profile_store()
    host_key = normalize_host(host)
    active = store.set_host_profile(host_key, profile_payload)
    return {
        "host": host_key,
        "active": active,
    }


def configure_host_learning(
    enabled: bool | None = None,
    apply_mode: str | None = None,
    threshold: int | None = None,
    profiles_path: str | None = None,
) -> dict:
    """Update host-learning settings in shared browser config."""
    return update_browser_config(
        host_learning_enabled=enabled,
        host_learning_apply_mode=apply_mode,
        host_learning_promotion_threshold=threshold,
        host_profiles_path=profiles_path,
    )


def get_current_config() -> dict:
    """Returns all current configuration settings."""
    return {
        "browser": GLOBAL_BROWSER_CONFIG.to_dict(),
        "crawler": {
            "respect_robots": GLOBAL_RESPECT_ROBOTS,
            "stealth_mode": GLOBAL_STEALTH_MODE,
            "max_depth": GLOBAL_CRAWLER_CONFIG.default_max_depth,
            "max_pages": GLOBAL_CRAWLER_CONFIG.default_max_pages,
        },
        "runtime": GLOBAL_RUNTIME_SETTINGS.as_dict(),
    }
