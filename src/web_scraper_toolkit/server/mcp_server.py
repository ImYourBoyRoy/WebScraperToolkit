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
from typing import Optional
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
    get_sitemap_urls
)

# Configure Logging
# FastMCP handles stdio/logging carefully, but we can still write to file
logging.basicConfig(
    filename='mcp_server.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp_server")

# --- SANDBOXING ---
# We keep your ProcessPoolExecutor. This is excellent architecture 
# because it prevents browser crashes from killing the MCP connection.
executor = ProcessPoolExecutor(max_workers=1)

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
        return await loop.run_in_executor(executor, _run_isolated_task, func, *args, **kwargs)
    except RuntimeError:
        # Fallback if no loop (unlikely in FastMCP async context but safe)
        return _run_isolated_task(func, *args, **kwargs)

# --- FASTMCP SERVER DEFINITION ---
mcp = FastMCP("WebScraperToolkit")

@mcp.tool()
async def scrape_url(url: str, format: str = "markdown") -> str:
    """
    Scrape a single URL and return content. Handles dynamic JS and Cloudflare.
    
    Args:
        url: Target HTTP/HTTPS URL.
        format: Output format. Options: 'markdown', 'text', 'html'.
    """
    logger.info(f"Tool Call: scrape_url (format={format}) for {url}")
    
    if format == "markdown":
        return await run_in_process(read_website_markdown, url)
    else:
        # Default to content (text/html logic handled inside read_website_content usually)
        return await run_in_process(read_website_content, url)

@mcp.tool()
async def search_web(query: str) -> str:
    """
    Search the web (DuckDuckGo / Google) for a query and return top results.
    """
    logger.info(f"Tool Call: search_web for '{query}'")
    return await run_in_process(general_web_search, query)

@mcp.tool()
async def get_sitemap(url: str) -> str:
    """
    Extract URLs from a website sitemap or analyze a landing page for links.
    """
    logger.info(f"Tool Call: get_sitemap for {url}")
    return await run_in_process(get_sitemap_urls, url)

@mcp.tool()
async def screenshot(url: str, path: str) -> str:
    """
    Capture a screenshot of a webpage.
    
    Args:
        url: Target URL.
        path: Local output path for PNG.
    """
    logger.info(f"Tool Call: screenshot {url} -> {path}")
    return await run_in_process(capture_screenshot, url, path)

def main():
    """Entry point for the MCP server."""
    mcp.run()

if __name__ == "__main__":
    main()
