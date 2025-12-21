# ./src/web_scraper_toolkit/server/mcp_tools/management.py
"""
Management MCP Tools
====================

Cache, session, history, configuration, and playbook tools.
"""

import logging

from ..handlers.playbook import execute_playbook
from ..handlers.config import (
    update_browser_config,
    update_stealth_config,
    get_current_config,
)
from ...core.state.cache import get_cache, clear_global_cache
from ...core.state.session import get_session_manager
from ...core.state.history import get_history_manager
from ...core.automation.retry import update_retry_config as _update_retry_config

logger = logging.getLogger("mcp_server")


def register_management_tools(mcp, create_envelope, format_error, run_in_process):
    """Register management and configuration tools."""

    # --- Configuration ---
    @mcp.tool()
    async def configure_scraper(headless: bool = True) -> str:
        """Configure browser settings."""
        try:
            logger.info(f"Tool Call: configure_scraper headless={headless}")
            update_browser_config(headless=headless)
            return create_envelope(
                "success",
                f"Browser set to {'headless' if headless else 'visible'} mode.",
                meta={"headless": headless},
            )
        except Exception as e:
            return format_error("configure_scraper", e)

    @mcp.tool()
    async def configure_stealth(
        respect_robots: bool = True,
        stealth_mode: bool = True,
    ) -> str:
        """Configure stealth mode and robots.txt compliance."""
        try:
            logger.info(f"Tool Call: configure_stealth respect_robots={respect_robots}")
            result = update_stealth_config(respect_robots=respect_robots)
            return create_envelope(
                "success", "Stealth configuration updated.", meta=result
            )
        except Exception as e:
            return format_error("configure_stealth", e)

    @mcp.tool()
    async def get_config() -> str:
        """Get current configuration settings."""
        try:
            config = get_current_config()
            return create_envelope("success", config)
        except Exception as e:
            return format_error("get_config", e)

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
            return create_envelope(
                "success", "Retry configuration updated", meta=result
            )
        except Exception as e:
            return format_error("configure_retry", e)

    # --- Cache Management ---
    @mcp.tool()
    async def clear_cache() -> str:
        """Clear the response cache. Use when cached data may be stale."""
        try:
            logger.info("Tool Call: clear_cache")
            result = clear_global_cache()
            return create_envelope("success", "Cache cleared", meta=result)
        except Exception as e:
            return format_error("clear_cache", e)

    @mcp.tool()
    async def get_cache_stats() -> str:
        """Get response cache statistics (hits, misses, size)."""
        try:
            cache = get_cache()
            stats = cache.get_stats()
            return create_envelope("success", stats)
        except Exception as e:
            return format_error("get_cache_stats", e)

    # --- Session Management ---
    @mcp.tool()
    async def clear_session(session_id: str = "default") -> str:
        """Clear a browser session (cookies, storage). Use for fresh starts."""
        try:
            logger.info(f"Tool Call: clear_session for {session_id}")
            session_mgr = get_session_manager()
            result = session_mgr.clear_session(session_id)
            return create_envelope("success", "Session cleared", meta=result)
        except Exception as e:
            return format_error("clear_session", e)

    @mcp.tool()
    async def new_session() -> str:
        """Start a fresh browser session, clearing all existing sessions."""
        try:
            logger.info("Tool Call: new_session")
            session_mgr = get_session_manager()
            result = session_mgr.clear_all_sessions()
            return create_envelope(
                "success", "All sessions cleared. New session ready.", meta=result
            )
        except Exception as e:
            return format_error("new_session", e)

    @mcp.tool()
    async def list_sessions() -> str:
        """List all saved browser sessions."""
        try:
            session_mgr = get_session_manager()
            sessions = session_mgr.list_sessions()
            return create_envelope("success", sessions, meta={"count": len(sessions)})
        except Exception as e:
            return format_error("list_sessions", e)

    # --- History ---
    @mcp.tool()
    async def get_history(limit: int = 10) -> str:
        """Get recent scraping history."""
        try:
            history_mgr = get_history_manager()
            entries = history_mgr.get_recent(limit)
            stats = history_mgr.get_stats()
            return create_envelope("success", {"entries": entries, "stats": stats})
        except Exception as e:
            return format_error("get_history", e)

    @mcp.tool()
    async def clear_history() -> str:
        """Clear scraping history."""
        try:
            history_mgr = get_history_manager()
            result = history_mgr.clear()
            return create_envelope("success", "History cleared", meta=result)
        except Exception as e:
            return format_error("clear_history", e)

    # --- Playbook ---
    @mcp.tool()
    async def run_playbook(playbook_json: str, proxies_json: str = None) -> str:
        """Execute an Autonomous Crawl using a Playbook."""
        try:
            logger.info("Tool Call: run_playbook")
            data = await execute_playbook(playbook_json, proxies_json)
            return create_envelope("success", data, meta={"action": "playbook_run"})
        except Exception as e:
            return format_error("run_playbook", e)

    logger.info("Registered: management tools (12)")
