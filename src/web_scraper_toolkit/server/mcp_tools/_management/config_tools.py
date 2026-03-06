# ./src/web_scraper_toolkit/server/mcp_tools/_management/config_tools.py
"""
Register management MCP tools related to configuration and runtime tuning.
Used by management facade during MCP startup registration sequence.
Run: imported and called from register_management_tools.
Inputs: registration context and incoming tool call parameters.
Outputs: JSON envelope payloads with updated configuration metadata.
Side effects: mutates runtime/browser/learning/retry configuration state.
Operational notes: preserves legacy tool names and response envelopes.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ....core.automation.retry import update_retry_config as _update_retry_config
from ...handlers.config import (
    clear_host_profile as clear_host_profile_record,
    configure_host_learning as configure_host_learning_settings,
    get_current_config,
    get_host_profiles as get_host_profiles_snapshot,
    refresh_runtime_config,
    set_host_profile as set_host_profile_record,
    update_browser_config,
    update_runtime_overrides,
    update_stealth_config,
)
from .context import ManagementRegistrationContext

logger = logging.getLogger("mcp_server")


def register_config_tools(ctx: ManagementRegistrationContext) -> None:
    """Register configuration and runtime management tool handlers."""
    mcp = ctx.mcp
    create_envelope = ctx.create_envelope
    format_error = ctx.format_error

    @mcp.tool()
    async def configure_scraper(
        headless: Optional[bool] = None,
        browser_type: Optional[str] = None,
        timeout_ms: Optional[int] = None,
        native_fallback_policy: Optional[str] = None,
        native_browser_channels: Optional[str] = None,
        native_browser_headless: Optional[bool] = None,
        native_context_mode: Optional[str] = None,
        native_profile_dir: Optional[str] = None,
        interactive_channel: Optional[str] = None,
        interactive_context_mode: Optional[str] = None,
        interactive_profile_dir: Optional[str] = None,
        host_profiles_enabled: Optional[bool] = None,
        host_profiles_path: Optional[str] = None,
        host_profiles_read_only: Optional[bool] = None,
        host_learning_enabled: Optional[bool] = None,
        host_learning_apply_mode: Optional[str] = None,
        host_learning_promotion_threshold: Optional[int] = None,
        restart_interactive_session: bool = False,
    ) -> str:
        """Configure browser settings."""
        try:
            logger.info(
                "Tool Call: configure_scraper headless=%s browser_type=%s timeout=%s "
                "native_fallback_policy=%s native_browser_channels=%s native_context_mode=%s "
                "interactive_channel=%s interactive_context_mode=%s host_profiles_enabled=%s "
                "host_profiles_read_only=%s host_learning_enabled=%s host_profiles_path=%s "
                "restart_interactive_session=%s",
                headless,
                browser_type,
                timeout_ms,
                native_fallback_policy,
                native_browser_channels,
                native_context_mode,
                interactive_channel,
                interactive_context_mode,
                host_profiles_enabled,
                host_profiles_read_only,
                host_learning_enabled,
                host_profiles_path,
                restart_interactive_session,
            )
            result = update_browser_config(
                headless=headless,
                browser_type=browser_type,
                timeout_ms=timeout_ms,
                native_fallback_policy=native_fallback_policy,
                native_browser_channels=native_browser_channels,
                native_browser_headless=native_browser_headless,
                native_context_mode=native_context_mode,
                native_profile_dir=native_profile_dir,
                interactive_channel=interactive_channel,
                interactive_context_mode=interactive_context_mode,
                interactive_profile_dir=interactive_profile_dir,
                host_profiles_enabled=host_profiles_enabled,
                host_profiles_path=host_profiles_path,
                host_profiles_read_only=host_profiles_read_only,
                host_learning_enabled=host_learning_enabled,
                host_learning_apply_mode=host_learning_apply_mode,
                host_learning_promotion_threshold=host_learning_promotion_threshold,
            )
            restarted = False
            if restart_interactive_session:
                from ...handlers.interactive import get_interactive_session

                session = get_interactive_session()
                if session.is_active:
                    await session.close()
                    restarted = True
            return create_envelope(
                "success",
                "Browser configuration updated.",
                meta={**result, "interactive_session_restarted": restarted},
            )
        except Exception as exc:
            return format_error("configure_scraper", exc)

    @mcp.tool()
    async def configure_stealth(
        respect_robots: bool = True,
        stealth_mode: bool = True,
    ) -> str:
        """Configure stealth mode and robots.txt compliance."""
        try:
            logger.info("Tool Call: configure_stealth respect_robots=%s", respect_robots)
            result = update_stealth_config(respect_robots=respect_robots)
            result["stealth_mode"] = stealth_mode
            return create_envelope("success", "Stealth configuration updated.", meta=result)
        except Exception as exc:
            return format_error("configure_stealth", exc)

    @mcp.tool()
    async def configure_runtime(overrides_json: str) -> str:
        """Apply runtime override values without restarting the MCP server."""
        try:
            overrides = json.loads(overrides_json)
            if not isinstance(overrides, dict):
                raise ValueError("overrides_json must decode to an object/dict")
            updated = update_runtime_overrides(overrides)
            return create_envelope(
                "success",
                {"message": "Runtime overrides applied.", "runtime": updated},
                meta={"updated_keys": list(overrides.keys())},
            )
        except Exception as exc:
            return format_error("configure_runtime", exc)

    @mcp.tool()
    async def reload_runtime_config(
        config_path: Optional[str] = None,
        local_config_path: Optional[str] = None,
    ) -> str:
        """Reload runtime settings from config files."""
        try:
            updated = refresh_runtime_config(
                config_json_path=config_path,
                local_cfg_path=local_config_path,
            )
            return create_envelope(
                "success",
                {"message": "Runtime config reloaded.", "runtime": updated},
                meta={"config_path": config_path, "local_config_path": local_config_path},
            )
        except Exception as exc:
            return format_error("reload_runtime_config", exc)

    @mcp.tool()
    async def get_config() -> str:
        """Get current configuration settings."""
        try:
            return create_envelope("success", get_current_config())
        except Exception as exc:
            return format_error("get_config", exc)

    @mcp.tool()
    async def get_host_profiles(host: Optional[str] = None) -> str:
        """Return host profile learning store (all hosts or one host)."""
        try:
            data = get_host_profiles_snapshot(host=host)
            return create_envelope(
                "success",
                data,
                meta={"host": host, "mode": "single" if host else "all"},
            )
        except Exception as exc:
            return format_error("get_host_profiles", exc)

    @mcp.tool()
    async def clear_host_profile(host: str) -> str:
        """Delete one host profile record from the profile store."""
        try:
            if not str(host or "").strip():
                raise ValueError("host is required")
            result = clear_host_profile_record(host)
            return create_envelope("success", result, meta={"host": host})
        except Exception as exc:
            return format_error("clear_host_profile", exc)

    @mcp.tool()
    async def set_host_profile(host: str, profile_json: str) -> str:
        """Set active host routing profile from JSON payload (admin override)."""
        try:
            if not str(host or "").strip():
                raise ValueError("host is required")
            profile_payload = json.loads(profile_json)
            if not isinstance(profile_payload, dict):
                raise ValueError("profile_json must decode to an object/dict")
            result = set_host_profile_record(host, profile_payload)
            return create_envelope("success", result, meta={"host": host})
        except Exception as exc:
            return format_error("set_host_profile", exc)

    @mcp.tool()
    async def configure_host_learning(
        enabled: Optional[bool] = None,
        apply_mode: Optional[str] = None,
        threshold: Optional[int] = None,
        profiles_path: Optional[str] = None,
    ) -> str:
        """Configure host-profile auto-learning behavior."""
        try:
            updated = configure_host_learning_settings(
                enabled=enabled,
                apply_mode=apply_mode,
                threshold=threshold,
                profiles_path=profiles_path,
            )
            return create_envelope(
                "success",
                "Host learning configuration updated.",
                meta=updated,
            )
        except Exception as exc:
            return format_error("configure_host_learning", exc)

    @mcp.tool()
    async def configure_retry(
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> str:
        """Configure retry behavior with exponential backoff."""
        try:
            result = _update_retry_config(
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                max_delay=max_delay,
            )
            return create_envelope("success", "Retry configuration updated", meta=result)
        except Exception as exc:
            return format_error("configure_retry", exc)
