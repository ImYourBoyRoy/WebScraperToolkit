# ./src/web_scraper_toolkit/server/mcp_tools/management.py
"""
Register MCP tools for runtime configuration, lifecycle management, and async jobs.
Used by `server/mcp_server.py` during tool registration.
Run: Imported by MCP server; not a direct command-line entry point.
Inputs: Config toggles, JSON override payloads, playbook payloads, and job control requests.
Outputs: JSON envelope payloads with status, runtime state, and queued/completed job results.
Side effects: Mutates global runtime/config state and creates in-memory async jobs.
Operational notes: Job tools prevent long-running agent calls from blocking MCP round-trips.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from ...core.automation.retry import update_retry_config as _update_retry_config
from ...core.state.cache import clear_global_cache, get_cache
from ...core.state.history import get_history_manager
from ...core.state.session import get_session_manager
from ...core.runtime import resolve_worker_count
from ..handlers.config import (
    get_current_config,
    get_runtime_config,
    refresh_runtime_config,
    update_browser_config,
    update_runtime_overrides,
    update_stealth_config,
)
from ..handlers.extraction import get_contacts
from ..handlers.playbook import execute_playbook
from ..handlers.scraping import scrape_batch
from ..handlers.search import perform_deep_research
from ..jobs import AsyncJobManager

logger = logging.getLogger("mcp_server")

_job_manager: Optional[AsyncJobManager] = None


def _get_job_manager() -> AsyncJobManager:
    """Lazily instantiate an async job manager from runtime settings."""
    global _job_manager
    runtime = get_runtime_config()
    if _job_manager is None:
        _job_manager = AsyncJobManager(
            retention_seconds=runtime.job_retention_seconds,
            max_records=runtime.max_job_records,
        )
        return _job_manager

    if (
        _job_manager.retention_seconds != runtime.job_retention_seconds
        or _job_manager.max_records != runtime.max_job_records
    ):
        _job_manager = AsyncJobManager(
            retention_seconds=runtime.job_retention_seconds,
            max_records=runtime.max_job_records,
        )
    return _job_manager


async def _batch_contacts_job(urls: list[str]) -> list[dict[str, Any]]:
    runtime = get_runtime_config()
    batch_workers = resolve_worker_count(
        runtime.concurrency.mcp_batch_workers
        if runtime.concurrency.mcp_batch_workers > 0
        else "auto",
        cpu_reserve=runtime.concurrency.cpu_reserve,
        max_workers=runtime.concurrency.crawler_max_workers,
        fallback=4,
    )
    semaphore = asyncio.Semaphore(batch_workers)

    async def _process(url: str) -> dict[str, Any]:
        async with semaphore:
            try:
                data = await asyncio.to_thread(get_contacts, url)
                if isinstance(data, dict):
                    return {"url": url, **data}
                return {"url": url, "data": data}
            except Exception as exc:
                return {"url": url, "error": str(exc)}

    return await asyncio.gather(*[_process(url) for url in urls])


def _job_builder_map() -> Dict[str, Callable[[Dict[str, Any]], Awaitable[Any]]]:
    async def _batch_scrape(payload: Dict[str, Any]) -> Any:
        urls = payload.get("urls", [])
        output_format = str(payload.get("format", "markdown"))
        if not isinstance(urls, list) or not urls:
            raise ValueError("payload.urls must be a non-empty list")
        return await scrape_batch(urls, format=output_format)

    async def _deep_research(payload: Dict[str, Any]) -> Any:
        query = str(payload.get("query", "")).strip()
        if not query:
            raise ValueError("payload.query is required")
        return await perform_deep_research(query)

    async def _playbook(payload: Dict[str, Any]) -> Any:
        playbook_json = payload.get("playbook_json")
        if not isinstance(playbook_json, str) or not playbook_json.strip():
            raise ValueError("payload.playbook_json must be a JSON string")
        proxies_json = payload.get("proxies_json")
        if proxies_json is not None and not isinstance(proxies_json, str):
            raise ValueError("payload.proxies_json must be a JSON string when provided")
        return await execute_playbook(playbook_json, proxies_json)

    async def _batch_contacts(payload: Dict[str, Any]) -> Any:
        urls = payload.get("urls", [])
        if not isinstance(urls, list) or not urls:
            raise ValueError("payload.urls must be a non-empty list")
        return await _batch_contacts_job([str(url) for url in urls])

    return {
        "batch_scrape": _batch_scrape,
        "deep_research": _deep_research,
        "run_playbook": _playbook,
        "batch_contacts": _batch_contacts,
    }


def register_management_tools(mcp, create_envelope, format_error, run_in_process):
    """Register management and configuration tools."""

    # --- Configuration ---
    @mcp.tool()
    async def configure_scraper(
        headless: bool = True,
        browser_type: str = "chromium",
        timeout_ms: int = 30000,
    ) -> str:
        """Configure browser settings."""
        try:
            logger.info(
                "Tool Call: configure_scraper headless=%s browser_type=%s timeout=%s",
                headless,
                browser_type,
                timeout_ms,
            )
            result = update_browser_config(
                headless=headless,
                browser_type=browser_type,
                timeout_ms=timeout_ms,
            )
            return create_envelope(
                "success",
                f"Browser set to {'headless' if headless else 'visible'} mode.",
                meta=result,
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
            logger.info(
                "Tool Call: configure_stealth respect_robots=%s", respect_robots
            )
            result = update_stealth_config(respect_robots=respect_robots)
            result["stealth_mode"] = stealth_mode
            return create_envelope(
                "success", "Stealth configuration updated.", meta=result
            )
        except Exception as e:
            return format_error("configure_stealth", e)

    @mcp.tool()
    async def configure_runtime(
        overrides_json: str,
    ) -> str:
        """
        Apply runtime override values without restarting the MCP server.

        Use this to tune concurrency, timeout profiles, and remote-server behavior dynamically.
        """
        try:
            overrides = json.loads(overrides_json)
            if not isinstance(overrides, dict):
                raise ValueError("overrides_json must decode to an object/dict")
            updated = update_runtime_overrides(overrides)
            return create_envelope(
                "success",
                {
                    "message": "Runtime overrides applied.",
                    "runtime": updated,
                },
                meta={"updated_keys": list(overrides.keys())},
            )
        except Exception as e:
            return format_error("configure_runtime", e)

    @mcp.tool()
    async def reload_runtime_config(
        config_path: Optional[str] = None,
        local_config_path: Optional[str] = None,
    ) -> str:
        """
        Reload runtime settings from config files.
        """
        try:
            updated = refresh_runtime_config(
                config_json_path=config_path,
                local_cfg_path=local_config_path,
            )
            return create_envelope(
                "success",
                {
                    "message": "Runtime config reloaded.",
                    "runtime": updated,
                },
                meta={
                    "config_path": config_path,
                    "local_config_path": local_config_path,
                },
            )
        except Exception as e:
            return format_error("reload_runtime_config", e)

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
            logger.info("Tool Call: clear_session for %s", session_id)
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
        except Exception as e:
            return format_error("run_playbook", e)

    # --- Async Jobs ---
    @mcp.tool()
    async def start_job(
        job_type: str,
        payload_json: str,
        timeout_profile: str = "research",
    ) -> str:
        """
        Start a long-running job and return immediately with a `job_id`.

        Supported job types: `batch_scrape`, `deep_research`, `run_playbook`, `batch_contacts`.
        """
        try:
            payload = json.loads(payload_json)
            if not isinstance(payload, dict):
                raise ValueError("payload_json must decode to a JSON object")

            builders = _job_builder_map()
            normalized_job_type = job_type.strip().lower()
            if normalized_job_type not in builders:
                raise ValueError(
                    f"Unsupported job_type '{job_type}'. "
                    f"Supported: {', '.join(sorted(builders.keys()))}"
                )

            runtime = get_runtime_config()
            profile = runtime.get_timeout_profile(timeout_profile)
            job_manager = _get_job_manager()
            job_id = await job_manager.submit(
                builders[normalized_job_type](payload),
                timeout_profile_name=timeout_profile,
                timeout_profile=profile,
                description=f"{normalized_job_type} async job",
                metadata={"job_type": normalized_job_type},
            )
            return create_envelope(
                "success",
                {"job_id": job_id},
                meta={
                    "job_type": normalized_job_type,
                    "timeout_profile": timeout_profile,
                },
            )
        except Exception as e:
            return format_error("start_job", e)

    @mcp.tool()
    async def poll_job(job_id: str, include_result: bool = True) -> str:
        """Get current status of a job started by `start_job`."""
        try:
            job_manager = _get_job_manager()
            job_data = await job_manager.poll(job_id, include_result=include_result)
            status = "success" if job_data.get("status") != "not_found" else "error"
            return create_envelope(status, job_data, meta={"job_id": job_id})
        except Exception as e:
            return format_error("poll_job", e)

    @mcp.tool()
    async def cancel_job(job_id: str) -> str:
        """Cancel a running async job."""
        try:
            job_manager = _get_job_manager()
            result = await job_manager.cancel(job_id)
            return create_envelope("success", result, meta={"job_id": job_id})
        except Exception as e:
            return format_error("cancel_job", e)

    @mcp.tool()
    async def list_jobs(limit: int = 20) -> str:
        """List recent async jobs and their statuses."""
        try:
            job_manager = _get_job_manager()
            result = await job_manager.list_jobs(limit=limit)
            return create_envelope("success", result, meta={"limit": limit})
        except Exception as e:
            return format_error("list_jobs", e)

    logger.info("Registered: management tools")
