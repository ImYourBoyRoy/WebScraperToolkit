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
from ..handlers.config import get_runtime_config
from ..path_safety import resolve_safe_output_path
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
        timeout_profile: str = "standard",
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
                timeout_profile=timeout_profile,
                work_units=max(1, max_length // 15000),
            )
            return create_envelope("success", data, meta={"url": url, "format": format})
        except Exception as e:
            return format_error("scrape_url", e)

    @mcp.tool()
    async def batch_scrape(
        urls: list[str],
        format: str = "markdown",
        timeout_profile: str = "research",
        workers: Optional[int] = None,
    ) -> str:
        """Scrape multiple URLs in parallel."""
        try:
            logger.info(f"Tool Call: batch_scrape for {len(urls)} URLs")
            data = await run_in_process(
                scrape_batch,
                urls,
                format=format,
                workers=workers,
                timeout_profile=timeout_profile,
                work_units=max(1, len(urls)),
            )
            return create_envelope(
                "success",
                data,
                meta={"count": len(urls), "format": format, "workers": workers},
            )
        except Exception as e:
            return format_error("batch_scrape", e)

    @mcp.tool()
    async def screenshot(
        url: str,
        path: str,
        timeout_profile: str = "standard",
    ) -> str:
        """Capture a screenshot of a webpage."""
        try:
            runtime = get_runtime_config()
            safe_path = resolve_safe_output_path(path, runtime.safe_output_root)
            logger.info(f"Tool Call: screenshot {url} -> {safe_path}")
            await run_in_process(
                take_screenshot,
                url,
                safe_path,
                timeout_profile=timeout_profile,
                work_units=2,
            )
            return create_envelope(
                "success",
                f"Screenshot saved to {safe_path}",
                meta={"url": url, "path": safe_path},
            )
        except Exception as e:
            return format_error("screenshot", e)

    @mcp.tool()
    async def save_pdf(
        url: str,
        path: str,
        timeout_profile: str = "research",
    ) -> str:
        """Save a URL as a PDF file."""
        try:
            runtime = get_runtime_config()
            safe_path = resolve_safe_output_path(path, runtime.safe_output_root)
            logger.info(f"Tool Call: save_pdf {url} -> {safe_path}")
            await run_in_process(
                save_url_pdf,
                url,
                safe_path,
                timeout_profile=timeout_profile,
                work_units=2,
            )
            return create_envelope(
                "success",
                f"PDF saved to {safe_path}",
                meta={"url": url, "path": safe_path},
            )
        except Exception as e:
            return format_error("save_pdf", e)

    @mcp.tool()
    async def get_metadata(url: str, timeout_profile: str = "standard") -> str:
        """Extract semantic metadata (JSON-LD, OpenGraph, TwitterCards)."""
        try:
            logger.info(f"Tool Call: get_metadata {url}")
            data = await run_in_process(
                _extract_metadata,
                url,
                timeout_profile=timeout_profile,
                work_units=1,
            )
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("get_metadata", e)

    logger.info("Registered: scraping tools (5)")
