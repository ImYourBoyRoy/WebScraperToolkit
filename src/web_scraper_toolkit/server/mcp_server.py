# ./src/web_scraper_toolkit/server/mcp_server.py
"""
MCP Server Module
=================

Implements the Model Context Protocol (MCP) server for the toolkit.
Exposes scraping capabilities to Agentic environments (Claude Desktop, etc.).

This file acts as the Gateway/Registry, delegating tool registration
to modular sub-packages in 'mcp_tools/'.

Tool Categories (34 total):
    - Scraping (5): scrape_url, batch_scrape, screenshot, save_pdf, get_metadata
    - Discovery (7): get_sitemap, crawl_site, extract_contacts, batch_contacts, extract_links, search_web, deep_research
    - Forms (7): fill_form, extract_tables, click_element, health_check, validate_url, detect_content_type, download_file
    - Content (3): chunk_text, get_token_count, truncate_text
    - Management (12): configure_*, cache, session, history, playbook
"""

import asyncio
import logging
import sys
import os
import signal
import argparse
from typing import Any, Dict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime

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
)


# --- CONFIGURATION (ENV VARS) ---
def get_worker_count():
    try:
        return int(os.environ.get("SCRAPER_WORKERS", "1"))
    except ValueError:
        return 1


executor = ProcessPoolExecutor(max_workers=get_worker_count())

# Configure Logging
logging.basicConfig(
    filename="mcp_server.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp_server")


# --- UTILITY FUNCTIONS ---
def create_envelope(status: str, data: Any, meta: Dict[str, Any] = None) -> str:
    """Create a standardized JSON envelope for tool outputs."""
    import json

    meta = meta or {}
    meta["timestamp"] = datetime.now().isoformat()
    envelope = {"status": status, "meta": meta, "data": data}
    return json.dumps(envelope, indent=2)


def format_error(func_name: str, error: Exception) -> str:
    """Format error message for the agent as a JSON envelope."""
    logger.error(f"MCP Tool Error in {func_name}: {error}", exc_info=True)
    return create_envelope(
        status="error",
        data=f"Error executing {func_name}: {str(error)}",
        meta={
            "function": func_name,
            "error_type": type(error).__name__,
        },
    )


async def run_in_process(func, *args, **kwargs):
    """Run a function in a process pool for isolation."""
    loop = asyncio.get_running_loop()
    if asyncio.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        from functools import partial

        call = partial(func, *args, **kwargs)
        return await loop.run_in_executor(executor, call)


# --- MCP SERVER SETUP ---
mcp = FastMCP("Web Scraper Toolkit")

# Register all tool categories
register_scraping_tools(mcp, create_envelope, format_error, run_in_process)
register_discovery_tools(mcp, create_envelope, format_error, run_in_process)
register_form_tools(mcp, create_envelope, format_error, run_in_process)
register_content_tools(mcp, create_envelope, format_error, run_in_process)
register_management_tools(mcp, create_envelope, format_error, run_in_process)

logger.info("MCP Server initialized with 34 tools")


# --- UI Utilities ---
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console()
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


def display_welcome():
    if not HAS_RICH:
        print("=== Web Scraper Toolkit MCP Server ===")
        print("Tools: 34 registered")
        return

    table = Table(title="Registered Tool Categories", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Tools", style="green")
    table.add_column("Count", style="yellow")

    table.add_row(
        "Scraping", "scrape_url, batch_scrape, screenshot, save_pdf, get_metadata", "5"
    )
    table.add_row(
        "Discovery",
        "get_sitemap, crawl_site, extract_contacts, batch_contacts, extract_links, search_web, deep_research",
        "7",
    )
    table.add_row(
        "Forms",
        "fill_form, extract_tables, click_element, health_check, validate_url, detect_content_type, download_file",
        "7",
    )
    table.add_row("Content", "chunk_text, get_token_count, truncate_text", "3")
    table.add_row("Management", "configure_*, cache, session, history, playbook", "12")

    console.print(
        Panel(table, title="[bold blue]Web Scraper Toolkit MCP Server[/bold blue]")
    )


# --- SIGNAL HANDLING ---
def signal_handler(sig, frame):
    logger.info("Shutdown signal received")
    executor.shutdown(wait=False)
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# --- MAIN ENTRY ---
def main():
    parser = argparse.ArgumentParser(
        description="Run MCP Server for Web Scraper Toolkit"
    )
    parser.add_argument(
        "--stdio", action="store_true", help="Run via stdio (for agents)"
    )
    parser.add_argument("--display", action="store_true", help="Display tools and exit")
    args = parser.parse_args()

    if args.display:
        display_welcome()
        return

    logger.info("Starting MCP Server...")
    display_welcome()
    mcp.run()


if __name__ == "__main__":
    main()
