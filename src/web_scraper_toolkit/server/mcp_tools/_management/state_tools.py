# ./src/web_scraper_toolkit/server/mcp_tools/_management/state_tools.py
"""
Register cache/session/history/playbook management MCP tools.
Used by management facade to keep tool registration modular.
Run: imported and executed from register_management_tools.
Inputs: management context and per-tool payload parameters.
Outputs: standardized envelopes for state and lifecycle operations.
Side effects: mutates cache/session/history state and executes playbooks.
Operational notes: preserves existing tool names and behavior contracts.
"""

from __future__ import annotations

import logging
from typing import Optional

from ....core.state.cache import clear_global_cache, get_cache
from ....core.state.history import get_history_manager
from ....core.state.session import get_session_manager
from ...handlers.playbook import execute_playbook
from .context import ManagementRegistrationContext

logger = logging.getLogger("mcp_server")


def register_state_tools(ctx: ManagementRegistrationContext) -> None:
    """Register cache/session/history/playbook management tools."""
    mcp = ctx.mcp
    create_envelope = ctx.create_envelope
    format_error = ctx.format_error
    run_in_process = ctx.run_in_process

    @mcp.tool()
    async def clear_cache() -> str:
        """Clear the response cache. Use when cached data may be stale."""
        try:
            logger.info("Tool Call: clear_cache")
            result = clear_global_cache()
            return create_envelope("success", "Cache cleared", meta=result)
        except Exception as exc:
            return format_error("clear_cache", exc)

    @mcp.tool()
    async def get_cache_stats() -> str:
        """Get response cache statistics (hits, misses, size)."""
        try:
            cache = get_cache()
            stats = cache.get_stats()
            return create_envelope("success", stats)
        except Exception as exc:
            return format_error("get_cache_stats", exc)

    @mcp.tool()
    async def clear_session(session_id: str = "default") -> str:
        """Clear a browser session (cookies, storage). Use for fresh starts."""
        try:
            logger.info("Tool Call: clear_session for %s", session_id)
            session_mgr = get_session_manager()
            result = session_mgr.clear_session(session_id)
            return create_envelope("success", "Session cleared", meta=result)
        except Exception as exc:
            return format_error("clear_session", exc)

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
        except Exception as exc:
            return format_error("new_session", exc)

    @mcp.tool()
    async def list_sessions() -> str:
        """List all saved browser sessions."""
        try:
            session_mgr = get_session_manager()
            sessions = session_mgr.list_sessions()
            return create_envelope("success", sessions, meta={"count": len(sessions)})
        except Exception as exc:
            return format_error("list_sessions", exc)

    @mcp.tool()
    async def get_history(limit: int = 10) -> str:
        """Get recent scraping history."""
        try:
            history_mgr = get_history_manager()
            entries = history_mgr.get_recent(limit)
            stats = history_mgr.get_stats()
            return create_envelope("success", {"entries": entries, "stats": stats})
        except Exception as exc:
            return format_error("get_history", exc)

    @mcp.tool()
    async def clear_history() -> str:
        """Clear scraping history."""
        try:
            history_mgr = get_history_manager()
            result = history_mgr.clear()
            return create_envelope("success", "History cleared", meta=result)
        except Exception as exc:
            return format_error("clear_history", exc)

    @mcp.tool()
    async def run_playbook(
        playbook_json: str,
        proxies_json: Optional[str] = None,
        timeout_profile: str = "research",
    ) -> str:
        """Execute an Autonomous Crawl using a Playbook."""
        try:
            logger.info("Tool Call: run_playbook")
            data = await run_in_process(
                execute_playbook,
                playbook_json,
                proxies_json,
                timeout_profile=timeout_profile,
                work_units=3,
            )
            return create_envelope("success", data, meta={"action": "playbook_run"})
        except Exception as exc:
            return format_error("run_playbook", exc)
