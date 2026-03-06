# ./src/web_scraper_toolkit/server/mcp_server.py
"""
Run and configure the Web Scraper Toolkit MCP server for local or remote agent workloads.
Used as the `web-scraper-server` entry point and as an importable MCP registry module.
Run: `web-scraper-server [--transport stdio|http|sse|streamable-http]`.
Inputs: CLI flags, env vars, config files, and runtime overrides for concurrency/timeouts.
Outputs: MCP tool registry and structured JSON envelopes for all tool responses.
Side effects: Starts MCP transports, process pools, async tasks, and optional API-key middleware.
Operational notes: Runtime precedence is CLI > ENV > settings.local.cfg/settings.cfg > config.json > defaults.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Awaitable, Dict, Optional
from weakref import WeakKeyDictionary

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..core.runtime import (
    RuntimeSettings,
    TimeoutProfile,
    load_runtime_settings,
    resolve_worker_count,
)
from .handlers.config import get_runtime_config, refresh_runtime_config

try:
    from fastmcp import FastMCP
except ImportError:
    print("Error: 'fastmcp' package not found. Install it with: pip install fastmcp")
    sys.exit(1)

# Import modular tool registrations
from .mcp_tools import (
    register_scraping_tools,
    register_discovery_tools,
    register_form_tools,
    register_content_tools,
    register_management_tools,
    register_browser_interactive_tools,
    register_diagnostics_tools,
)


logger = logging.getLogger("mcp_server")
LOG_DIR = Path(os.getenv("WST_LOG_DIR", "logs")).resolve()
LOG_DIR.mkdir(parents=True, exist_ok=True)
MCP_SERVER_LOG_PATH = LOG_DIR / "mcp_server.log"
logging.basicConfig(
    filename=str(MCP_SERVER_LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class ApiKeyAuthMiddleware(BaseHTTPMiddleware):
    """Simple API-key middleware for remote HTTP/SSE MCP endpoints."""

    def __init__(self, app: Any, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        header_key = request.headers.get("x-api-key", "")
        bearer = request.headers.get("authorization", "")
        bearer_key = ""
        if bearer.lower().startswith("bearer "):
            bearer_key = bearer[7:].strip()

        if header_key != self.api_key and bearer_key != self.api_key:
            return JSONResponse(
                {"error": "Unauthorized: missing or invalid API key"},
                status_code=401,
            )
        return await call_next(request)


def _runtime_to_worker_count(settings: RuntimeSettings) -> int:
    requested: str | int = (
        settings.concurrency.mcp_process_workers
        if settings.concurrency.mcp_process_workers > 0
        else "auto"
    )
    return resolve_worker_count(
        requested,
        cpu_reserve=settings.concurrency.cpu_reserve,
        max_workers=settings.concurrency.crawler_max_workers,
        fallback=1,
    )


def _runtime_to_inflight_limit(settings: RuntimeSettings) -> int:
    requested: str | int = (
        settings.concurrency.mcp_inflight_limit
        if settings.concurrency.mcp_inflight_limit > 0
        else "auto"
    )
    return resolve_worker_count(
        requested,
        cpu_reserve=settings.concurrency.cpu_reserve,
        max_workers=max(1, settings.concurrency.crawler_max_workers * 2),
        fallback=4,
    )


RUNTIME_SETTINGS: RuntimeSettings = load_runtime_settings()
PROCESS_WORKERS = _runtime_to_worker_count(RUNTIME_SETTINGS)
INFLIGHT_LIMIT = _runtime_to_inflight_limit(RUNTIME_SETTINGS)

executor = ProcessPoolExecutor(max_workers=PROCESS_WORKERS)
_loop_semaphores: "WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = (
    WeakKeyDictionary()
)


def _set_runtime_settings(settings: RuntimeSettings) -> None:
    """Apply runtime settings and rebuild process/runtime controls."""
    global RUNTIME_SETTINGS, PROCESS_WORKERS, INFLIGHT_LIMIT, executor

    RUNTIME_SETTINGS = settings
    PROCESS_WORKERS = _runtime_to_worker_count(settings)
    INFLIGHT_LIMIT = _runtime_to_inflight_limit(settings)

    existing_executor = executor
    executor = ProcessPoolExecutor(max_workers=PROCESS_WORKERS)
    _loop_semaphores.clear()

    try:
        existing_executor.shutdown(wait=False)
    except Exception:
        logger.warning("Failed to gracefully shutdown previous process pool.")

    logger.info(
        "Runtime updated: workers=%s inflight_limit=%s timeout_profile=%s",
        PROCESS_WORKERS,
        INFLIGHT_LIMIT,
        RUNTIME_SETTINGS.default_timeout_profile,
    )


def _sync_runtime_state_if_needed() -> None:
    settings = get_runtime_config()
    desired_workers = _runtime_to_worker_count(settings)
    desired_limit = _runtime_to_inflight_limit(settings)

    if desired_workers != PROCESS_WORKERS or desired_limit != INFLIGHT_LIMIT:
        _set_runtime_settings(settings)


def _get_loop_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    semaphore = _loop_semaphores.get(loop)
    if semaphore is None:
        semaphore = asyncio.Semaphore(INFLIGHT_LIMIT)
        _loop_semaphores[loop] = semaphore
    return semaphore


async def _await_with_timeout(
    awaitable: Awaitable[Any],
    timeout_profile: TimeoutProfile,
) -> Any:
    if timeout_profile.hard_seconds <= 0:
        return await awaitable

    task = asyncio.ensure_future(awaitable)

    try:
        return await asyncio.wait_for(
            asyncio.shield(task),
            timeout=timeout_profile.soft_seconds,
        )
    except asyncio.TimeoutError:
        if not timeout_profile.allow_extension:
            task.cancel()
            raise TimeoutError(
                f"Task exceeded timeout ({timeout_profile.soft_seconds}s)."
            ) from None

        extension_cap = max(
            0, timeout_profile.hard_seconds - timeout_profile.soft_seconds
        )
        extension_seconds = min(timeout_profile.extension_seconds, extension_cap)
        if extension_seconds <= 0:
            task.cancel()
            raise TimeoutError(
                f"Task exceeded hard timeout ({timeout_profile.hard_seconds}s)."
            ) from None

        try:
            return await asyncio.wait_for(
                asyncio.shield(task),
                timeout=extension_seconds,
            )
        except asyncio.TimeoutError:
            task.cancel()
            raise TimeoutError(
                f"Task exceeded hard timeout ({timeout_profile.hard_seconds}s)."
            ) from None


def create_envelope(status: str, data: Any, meta: Dict[str, Any] | None = None) -> str:
    """Create a standardized JSON envelope for tool outputs."""
    import json

    envelope_meta = meta.copy() if isinstance(meta, dict) else {}
    envelope_meta["timestamp"] = datetime.now().isoformat()
    envelope = {"status": status, "meta": envelope_meta, "data": data}
    return json.dumps(envelope, indent=2)


def format_error(func_name: str, error: Exception) -> str:
    """Format error message for the agent as a JSON envelope."""
    logger.error("MCP Tool Error in %s: %s", func_name, error, exc_info=True)
    return create_envelope(
        status="error",
        data=f"Error executing {func_name}: {str(error)}",
        meta={
            "function": func_name,
            "error_type": type(error).__name__,
        },
    )


async def run_in_process(
    func: Any,
    *args: Any,
    timeout_profile: str | None = None,
    work_units: int = 1,
    disable_timeout: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Run a function in a process pool with adaptive timeout and backpressure controls.

    - `timeout_profile`: timeout profile name (`fast|standard|research|long`)
    - `work_units`: scales timeout budget dynamically
    """
    _sync_runtime_state_if_needed()

    current_runtime = get_runtime_config()
    profile_name = (timeout_profile or current_runtime.default_timeout_profile).lower()
    profile = current_runtime.get_timeout_profile(profile_name).scaled(work_units)
    profile_for_meta = profile.as_dict()

    semaphore = _get_loop_semaphore()
    async with semaphore:
        loop = asyncio.get_running_loop()
        if asyncio.iscoroutinefunction(func):
            operation = func(*args, **kwargs)
        else:
            operation = loop.run_in_executor(executor, partial(func, *args, **kwargs))

        if disable_timeout or profile_name in {"off", "none", "disabled"}:
            return await operation

        try:
            return await _await_with_timeout(operation, profile)
        except TimeoutError as timeout_exc:
            logger.warning(
                "Timeout executing %s with profile=%s budget=%s",
                getattr(func, "__name__", str(func)),
                profile_name,
                profile_for_meta,
            )
            raise timeout_exc


# --- MCP SERVER SETUP ---
mcp = FastMCP("Web Scraper Toolkit")

# Register all tool categories
register_scraping_tools(mcp, create_envelope, format_error, run_in_process)
register_discovery_tools(mcp, create_envelope, format_error, run_in_process)
register_form_tools(mcp, create_envelope, format_error, run_in_process)
register_content_tools(mcp, create_envelope, format_error, run_in_process)
register_management_tools(mcp, create_envelope, format_error, run_in_process)
register_browser_interactive_tools(mcp, create_envelope, format_error, run_in_process)
register_diagnostics_tools(mcp, create_envelope, format_error, run_in_process)

logger.info("MCP Server initialized with tool registry")


try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def display_welcome() -> None:
    if not HAS_RICH:
        print("=== Web Scraper Toolkit MCP Server ===")
        print("Transport-ready with runtime configuration controls")
        return

    table = Table(title="Runtime Snapshot", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Process Workers", str(PROCESS_WORKERS))
    table.add_row("In-flight Limit", str(INFLIGHT_LIMIT))
    table.add_row("Timeout Profile", RUNTIME_SETTINGS.default_timeout_profile)
    table.add_row("Safe Output Root", RUNTIME_SETTINGS.safe_output_root)
    table.add_row("Server Transport", RUNTIME_SETTINGS.server.transport)
    table.add_row("Server Host", RUNTIME_SETTINGS.server.host)
    table.add_row("Server Port", str(RUNTIME_SETTINGS.server.port))

    console.print(
        Panel(table, title="[bold blue]Web Scraper Toolkit MCP Server[/bold blue]")
    )


def _build_middleware(api_key: Optional[str]) -> list[Middleware] | None:
    if not api_key:
        return None
    return [Middleware(ApiKeyAuthMiddleware, api_key=api_key)]


def _normalize_tool_mapping(raw_tools: Any) -> Dict[str, Any]:
    """Normalize FastMCP tool registries across API versions."""
    if isinstance(raw_tools, dict):
        return dict(raw_tools)

    normalized: Dict[str, Any] = {}
    if isinstance(raw_tools, (list, tuple, set)):
        for tool in raw_tools:
            tool_name = getattr(tool, "name", None)
            if isinstance(tool_name, str) and tool_name:
                normalized[tool_name] = tool
    return normalized


async def get_registered_tools() -> Dict[str, Any]:
    """Return registered tools with compatibility for multiple FastMCP versions."""
    for getter_name in ("get_tools", "list_tools", "_list_tools"):
        direct_getter = getattr(mcp, getter_name, None)
        if not callable(direct_getter):
            continue

        direct_value = direct_getter()
        if asyncio.iscoroutine(direct_value):
            direct_value = await direct_value
        normalized = _normalize_tool_mapping(direct_value)
        if normalized:
            return normalized

    tool_manager = getattr(mcp, "_tool_manager", None)
    if tool_manager is not None:
        for getter_name in ("get_tools", "list_tools"):
            manager_getter = getattr(tool_manager, getter_name, None)
            if not callable(manager_getter):
                continue
            manager_value = manager_getter()
            if asyncio.iscoroutine(manager_value):
                manager_value = await manager_value
            normalized = _normalize_tool_mapping(manager_value)
            if normalized:
                return normalized

        manager_tools = getattr(tool_manager, "_tools", None)
        normalized = _normalize_tool_mapping(manager_tools)
        if normalized:
            return normalized

    return {}


def signal_handler(sig: int, frame: Any) -> None:
    logger.info("Shutdown signal received")
    executor.shutdown(wait=False)
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run MCP Server for Web Scraper Toolkit"
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run via stdio transport (for local agent integrations).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse", "streamable-http"],
        help="Explicit transport mode for MCP server.",
    )
    parser.add_argument("--host", type=str, help="Host for HTTP/SSE transport.")
    parser.add_argument("--port", type=int, help="Port for HTTP/SSE transport.")
    parser.add_argument("--path", type=str, help="HTTP path for remote MCP endpoint.")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json (runtime + toolkit settings).",
    )
    parser.add_argument(
        "--local-config",
        type=str,
        default=None,
        help="Path to local settings cfg (overrides config.json).",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Static API key for remote transport protection.",
    )
    parser.add_argument(
        "--api-key-env",
        type=str,
        default=None,
        help="Env var name containing API key (default from runtime settings).",
    )
    parser.add_argument(
        "--display", action="store_true", help="Display runtime and exit"
    )
    args = parser.parse_args()

    refresh_runtime_config(
        config_json_path=args.config, local_cfg_path=args.local_config
    )
    settings = get_runtime_config()
    _set_runtime_settings(settings)

    if args.display:
        display_welcome()
        return

    transport = "stdio" if args.stdio else (args.transport or settings.server.transport)
    host = args.host or settings.server.host
    port = args.port or settings.server.port
    path = args.path or settings.server.path

    api_key_env_name = args.api_key_env or settings.server.api_key_env
    api_key = args.api_key or os.environ.get(api_key_env_name)
    require_api_key = settings.server.require_api_key
    if api_key is None and require_api_key and transport != "stdio":
        raise RuntimeError(
            f"API key is required for remote transport. Set {api_key_env_name} or use --api-key."
        )

    middleware = _build_middleware(api_key if transport != "stdio" else None)

    logger.info(
        "Starting MCP server transport=%s host=%s port=%s path=%s workers=%s inflight_limit=%s",
        transport,
        host,
        port,
        path,
        PROCESS_WORKERS,
        INFLIGHT_LIMIT,
    )
    display_welcome()

    run_kwargs: Dict[str, Any] = {
        "transport": transport,
        "show_banner": settings.server.expose_server_banner,
    }
    if transport != "stdio":
        run_kwargs.update(
            {
                "host": host,
                "port": port,
                "path": path,
                "middleware": middleware,
            }
        )
    mcp.run(**run_kwargs)


if __name__ == "__main__":
    main()
