# ./src/web_scraper_toolkit/server/mcp_tools/scraping.py
"""
Scraping MCP Tools
==================

Core scraping tools: scrape_url, batch_scrape, screenshot, save_pdf, get_metadata.
"""

import logging
from typing import Optional

from ..handlers.scraping import (
    scrape_single_url,
    scrape_batch,
    take_screenshot,
    save_url_pdf,
)
from ...parsers.extraction.metadata import extract_metadata as _extract_metadata

logger = logging.getLogger("mcp_server")


def register_scraping_tools(mcp, create_envelope, format_error, run_in_process):
    """Register scraping-related MCP tools."""

    @mcp.tool()
    async def scrape_url(
        url: str,
        selector: Optional[str] = None,
        max_length: int = 50000,
        format: str = "markdown",
    ) -> str:
        """
        Scrape a URL and return its content.
        Primary tool for content acquisition.
        """
        try:
            logger.info(f"Tool Call: scrape_url {url}")
            data = await run_in_process(
                scrape_single_url,
                url,
                selector=selector,
                format=format,
                max_length=max_length,
            )
            return create_envelope("success", data, meta={"url": url, "format": format})
        except Exception as e:
            return format_error("scrape_url", e)

    @mcp.tool()
    async def batch_scrape(urls: list[str], format: str = "markdown") -> str:
        """Scrape multiple URLs in parallel."""
        try:
            logger.info(f"Tool Call: batch_scrape for {len(urls)} URLs")
            data = await run_in_process(scrape_batch, urls, format=format)
            return create_envelope(
                "success", data, meta={"count": len(urls), "format": format}
            )
        except Exception as e:
            return format_error("batch_scrape", e)

    @mcp.tool()
    async def screenshot(url: str, path: str) -> str:
        """Capture a screenshot of a webpage."""
        try:
            logger.info(f"Tool Call: screenshot {url} -> {path}")
            await run_in_process(take_screenshot, url, path)
            return create_envelope(
                "success",
                f"Screenshot saved to {path}",
                meta={"url": url, "path": path},
            )
        except Exception as e:
            return format_error("screenshot", e)

    @mcp.tool()
    async def save_pdf(url: str, path: str) -> str:
        """Save a URL as a PDF file."""
        try:
            logger.info(f"Tool Call: save_pdf {url} -> {path}")
            await run_in_process(save_url_pdf, url, path)
            return create_envelope(
                "success", f"PDF saved to {path}", meta={"url": url, "path": path}
            )
        except Exception as e:
            return format_error("save_pdf", e)

    @mcp.tool()
    async def get_metadata(url: str) -> str:
        """Extract semantic metadata (JSON-LD, OpenGraph, TwitterCards)."""
        try:
            logger.info(f"Tool Call: get_metadata {url}")
            data = await run_in_process(_extract_metadata, url)
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("get_metadata", e)

    logger.info("Registered: scraping tools (5)")
