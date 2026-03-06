# ./src/web_scraper_toolkit/server/mcp_tools/management.py
"""
Register MCP tools for runtime configuration, lifecycle management, and async jobs.
Used by `server/mcp_server.py` during tool registration.
Run: Imported by MCP server; not a direct command-line entry point.
Inputs: Config toggles, JSON override payloads, playbook payloads, and job control requests.
Outputs: JSON envelope payloads with status, runtime state, and queued/completed job results.
Side effects: Mutates global runtime/config state and creates in-memory async jobs.
Operational notes: registration internals are split into private _management modules.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from ...core.runtime import resolve_worker_count
from ..handlers.config import get_runtime_config
from ..handlers.extraction import get_contacts
from ..handlers.playbook import execute_playbook
from ..handlers.scraping import scrape_batch
from ..handlers.search import perform_deep_research
from ..jobs import AsyncJobManager
from ._management import register_config_tools, register_job_tools, register_state_tools
from ._management.context import ManagementRegistrationContext

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
    ctx = ManagementRegistrationContext(
        mcp=mcp,
        create_envelope=create_envelope,
        format_error=format_error,
        run_in_process=run_in_process,
        get_job_manager=_get_job_manager,
        job_builder_map=_job_builder_map,
    )
    register_config_tools(ctx)
    register_state_tools(ctx)
    register_job_tools(ctx)
    logger.info("Registered: management tools")
