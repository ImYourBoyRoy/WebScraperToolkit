# ./src/web_scraper_toolkit/server/mcp_server.py
"""
MCP Server Module
=================

Implements the Model Context Protocol (MCP) server for the toolkit.
Exposes scraping capabilities to Agentic environments (Claude Desktop, etc.).

Usage:
    python -m src.web_scraper_toolkit.server.mcp_server
    OR
    from src.web_scraper_toolkit.server import mcp; mcp.run()

Key Tools:
    - scrape_url: text/markdown extraction.
    - search_web: DuckDuckGo search.
    - get_sitemap: Sitemap analysis.
    - screenshot: Visual capture.

Operational Notes:
    - Uses ProcessPoolExecutor to sandbox scraping tasks.
    - Prevents browser crashes from killing the agent connection.
    - Uses 'fastmcp' framework.
"""

import asyncio
import logging
import sys
from typing import Any, Dict
from concurrent.futures import ProcessPoolExecutor

try:
    # "fastmcp" is the high-level framework you want to use.
    # Install via: pip install fastmcp
    from fastmcp import FastMCP
except ImportError:
    print("Error: 'fastmcp' package not found. Install it with: pip install fastmcp")
    sys.exit(1)

# Toolkit Imports
from ..parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    general_web_search,
    capture_screenshot,
    get_sitemap_urls,
    deep_research_with_google,
    save_as_pdf,
)

from ..browser.crawler import WebCrawler
from ..core.config import ScraperConfig
import json
from datetime import datetime
import argparse
import signal

# --- CONFIGURATION (ENV VARS) ---
# Allow easier docker/cli configuration of workers
import os


def get_worker_count():
    try:
        return int(os.environ.get("SCRAPER_WORKERS", "1"))
    except ValueError:
        return 1


executor = ProcessPoolExecutor(max_workers=get_worker_count())

# Global Config State (Persisted in memory for the session)
# This allows the 'configure_scraper' tool to affect subsequent calls
GLOBAL_CONFIG = ScraperConfig.load(
    {"scraper_settings": {"headless": True}, "workers": get_worker_count()}
)

# Configure Logging
# FastMCP handles stdio/logging carefully, but we can still write to file
logging.basicConfig(
    filename="mcp_server.log",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("mcp_server")


def create_envelope(status: str, data: Any, meta: Dict[str, Any] = None) -> str:
    """Create a standardized JSON envelope for tool outputs."""
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
            "tool": func_name,
            "suggestion": "Check the URL, try a different tool (like search_web), or retry with a simpler query.",
        },
    )


def _run_isolated_task(func, *args, **kwargs):
    """Helper to run a function in the separate process."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        # Re-raising allows FastMCP to catch it and format the error
        raise e


async def run_in_process(func, *args, **kwargs):
    """Runs a blocking task in the process pool."""
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            executor, _run_isolated_task, func, *args, **kwargs
        )
    except RuntimeError:
        # Fallback if no loop (unlikely in FastMCP async context but safe)
        return _run_isolated_task(func, *args, **kwargs)


# --- FASTMCP SERVER DEFINITION ---
mcp = FastMCP("WebScraperToolkit")


@mcp.tool()
async def scrape_url(
    url: str, format: str = "markdown", selector: str = None, max_length: int = 20000
) -> str:
    """
    Scrape a single URL. Handles dynamic JS/Cloudflare.
    Returns a structured JSON envelope.

    Args:
        url: Target HTTP/HTTPS URL.
        format: 'markdown' (default), 'text', 'html'.
        selector: CSS selector to extract specific content (e.g. 'main', '#article').
        max_length: Max characters to return (default 20k) to save tokens.
    """
    try:
        logger.info(f"Tool Call: scrape_url (format={format}) for {url}")

        if format == "markdown":
            data = await run_in_process(
                read_website_markdown,
                url,
                config=GLOBAL_CONFIG.to_dict(),
                selector=selector,
                max_length=max_length,
            )
        else:
            data = await run_in_process(
                read_website_content, url, config=GLOBAL_CONFIG.to_dict()
            )

        return create_envelope("success", data, meta={"url": url, "format": format})
    except Exception as e:
        return format_error("scrape_url", e)


@mcp.tool()
async def batch_scrape(urls: list[str], format: str = "markdown") -> str:
    """
    Scrape multiple URLs in parallel. efficiently.
    Returns a dictionary of results keyed by URL.

    Args:
        urls: List of URLs to scrape.
        format: 'markdown' (default) or 'text'.
    """
    try:
        logger.info(f"Tool Call: batch_scrape for {len(urls)} URLs")

        # Use WebCrawler for batch orchestration
        crawler = WebCrawler(config=GLOBAL_CONFIG)

        # Run crawler (returns list of results)
        await crawler.run(
            urls=urls,
            output_format=format,
            export=False,  # We want data back in memory
            merge=False,
        )

        # WebCrawler returns (content, outfile) pairs. We just want content.
        # But wait, crawler.run returns (content, outfile) tuples?
        # Actually crawler.run logic is: collected_outputs.append(content)
        # It's a bit complex. Let's look at crawler.run ... it returns None?
        # Ah, looking at crawler.py: "return" at end? No, it prints "Done".
        # It seems crawler.run DOES NOT return the data cleanly in current impl?
        # Re-reading crawler.py: "results = await asyncio.gather(*tasks)". Yes.
        # But the function itself `async def run(...)` creates `collected_outputs` but doesn't return them?
        # Critical Fix: We need to modify WebCrawler.run to return results, OR we create a temporary specialized batch runner here.
        # Since I can't easily change crawler.py return without checking CLI impact,
        # I will use `process_single_url` in parallel here directly.

        tasks = []
        for i, url in enumerate(urls):
            tasks.append(
                crawler.process_single_url(
                    index=i,
                    total=len(urls),
                    url=url,
                    output_format=format,
                    export=False,
                    merge=False,
                    output_dir=".",
                )
            )

        raw_results = await asyncio.gather(*tasks)

        # Format map: {url: content}
        output_map = {}
        failed = []

        for i, (content, _) in enumerate(raw_results):
            if content:
                output_map[urls[i]] = content
            else:
                failed.append(urls[i])
                output_map[urls[i]] = "Error: Failed to scrape."

        return create_envelope(
            "success",
            output_map,
            meta={"processed": len(urls), "failed": len(failed), "failed_urls": failed},
        )

    except Exception as e:
        return format_error("batch_scrape", e)


@mcp.tool()
async def configure_scraper(headless: bool = True, user_agent: str = None) -> str:
    """
    Update global scraper configuration.

    Args:
        headless: Run browser in headless mode (default: True). Set False for debugging.
        user_agent: Custom User-Agent string.
    """
    try:
        GLOBAL_CONFIG.scraper_settings.headless = headless
        if user_agent:
            GLOBAL_CONFIG.scraper_settings.user_agent = user_agent

        return create_envelope(
            "success",
            "Configuration updated",
            meta={"headless": headless, "user_agent": user_agent or "default"},
        )
    except Exception as e:
        return format_error("configure_scraper", e)


@mcp.tool()
async def search_web(query: str) -> str:
    """
    Search the web (DuckDuckGo / Google) for a query and return top results.
    """
    try:
        logger.info(f"Tool Call: search_web for '{query}'")
        data = await run_in_process(
            general_web_search, query, config=GLOBAL_CONFIG.to_dict()
        )
        return create_envelope("success", data, meta={"query": query})
    except Exception as e:
        return format_error("search_web", e)


@mcp.tool()
async def get_sitemap(url: str) -> str:
    """
    Extract URLs from a website sitemap.
    Useful for discovering all pages on a site.
    """
    try:
        logger.info(f"Tool Call: get_sitemap for {url}")
        data = await run_in_process(get_sitemap_urls, url)
        return create_envelope("success", data, meta={"url": url})
    except Exception as e:
        return format_error("get_sitemap", e)


@mcp.tool()
async def crawl_site(url: str) -> str:
    """
    Alias for get_sitemap.
    Discover all navigable links from a sitemap or landing page.
    """
    try:
        logger.info(f"Tool Call: crawl_site for {url}")
        data = await run_in_process(get_sitemap_urls, url)
        return create_envelope("success", data, meta={"url": url})
    except Exception as e:
        return format_error("crawl_site", e)


@mcp.tool()
async def screenshot(url: str, path: str) -> str:
    """
    Capture a screenshot of a webpage.

    Args:
        url: Target URL.
        path: Local output path for PNG.
    """
    try:
        logger.info(f"Tool Call: screenshot {url} -> {path}")
        data = await run_in_process(
            capture_screenshot, url, path, config=GLOBAL_CONFIG.to_dict()
        )
        return create_envelope("success", data, meta={"url": url, "path": path})
    except Exception as e:
        return format_error("screenshot", e)


@mcp.tool()
async def save_pdf(url: str, path: str) -> str:
    """
    Save a URL as a PDF file.

    Args:
        url: Target URL.
        path: Local output path for PDF.
    """
    try:
        logger.info(f"Tool Call: save_pdf {url} -> {path}")
        data = await run_in_process(
            save_as_pdf, url, path, config=GLOBAL_CONFIG.to_dict()
        )
        return create_envelope("success", data, meta={"url": url, "path": path})
    except Exception as e:
        return format_error("save_pdf", e)


@mcp.tool()
async def deep_research(query: str) -> str:
    """
    Perform a Deep Research task on a query.
    1. Searches DuckDuckGo for top results.
    2. Crawls the top 3 results for full content.
    3. Returns a consolidated report.

    Args:
        query: The topic or question to research.
    """
    try:
        logger.info(f"Tool Call: deep_research for '{query}'")
        data = await run_in_process(
            deep_research_with_google, query, config=GLOBAL_CONFIG.to_dict()
        )
        return create_envelope("success", data, meta={"query": query})
    except Exception as e:
        return format_error("deep_research", e)


# Try imports for Rich
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
except ImportError:
    # Fallback if rich not installed (though it is a dep)
    Console = None


def print_banner(verbose: bool):
    """Print a startup banner with server info."""
    if not Console:
        print("🚀 WebScraperToolkit MCP Server - ONLINE")
        return

    console = Console()
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Server", "WebScraperToolkit MCP")
    table.add_row("Status", "🟢 ONLINE")
    table.add_row("Python", sys.version.split()[0])
    table.add_row("Mode", "Verbose" if verbose else "Standard")

    # Try to get version
    try:
        from ... import __version__

        table.add_row("Version", __version__)
    except ImportError:
        pass

    console.print(Panel(table, title="🚀 Server Interface", border_style="blue"))

    tool_table = Table(title="Available Tools", show_header=True)
    tool_table.add_column("Tool Name", style="bold yellow")
    tool_table.add_column("Description", style="white")

    tools = [
        ("scrape_url", "Scrape single URL to Markdown/Text"),
        ("deep_research", "Deep research (Search + Crawl + Report)"),
        ("save_pdf", "Save URL as high-fidelity PDF"),
        ("search_web", "Google/DDG Search integration"),
        ("get_sitemap", "Sitemap parsing and link discovery"),
        ("crawl_site", "Alias for sitemap discovery"),
        ("screenshot", "Capture page screenshot"),
    ]

    for name, desc in tools:
        tool_table.add_row(name, desc)

    console.print(tool_table)
    console.print("\n[dim]Press Ctrl+C to stop the server.[/dim]\n")


def handle_sigint(signum, frame):
    if Console:
        Console().print("\n[bold red]🛑 Server stopping...[/bold red]")
    else:
        print("\n🛑 Server stopping...")
    sys.exit(0)


def main():
    """Entry point for the MCP server."""
    parser = argparse.ArgumentParser(
        description="Run the Web Scraper Toolkit MCP Server.",
        epilog="Designed for Agentic Integration.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging."
    )
    parser.add_argument(
        "--workers", type=int, help="Override default worker count (default: 1)."
    )

    args = parser.parse_args()

    # Set Environment Variable for MCP Server to pick up
    if args.workers:
        os.environ["SCRAPER_WORKERS"] = str(args.workers)

    if args.verbose:
        os.environ["SCRAPER_VERBOSE"] = "true"

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        print_banner(args.verbose)
        mcp.run()
    except Exception as e:
        print(f"❌ Server start failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
