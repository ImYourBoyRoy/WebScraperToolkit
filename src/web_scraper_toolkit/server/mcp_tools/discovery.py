# ./src/web_scraper_toolkit/server/mcp_tools/discovery.py
"""
Discovery MCP Tools
===================

Sitemap discovery, contact extraction, link extraction, and site exploration tools.
"""

import asyncio
import logging
import os
from typing import Optional

from ..handlers.search import perform_search, perform_deep_research
from ..handlers.extraction import discover_sitemap, get_contacts, get_sitemap_plain
from ...parsers.extraction.links import extract_links as _extract_links

logger = logging.getLogger("mcp_server")


def register_discovery_tools(mcp, create_envelope, format_error, run_in_process):
    """Register discovery-related MCP tools."""

    @mcp.tool()
    async def get_sitemap(
        url: str,
        keywords: Optional[str] = None,
        limit: int = 100,
    ) -> str:
        """
        Smart Sitemap Discovery and Filtering.
        Use 'keywords' to filter (e.g. 'team', 'about' for finding people pages).
        """
        try:
            logger.info(f"Tool Call: get_sitemap {url}")
            data = await run_in_process(
                discover_sitemap, url, keywords=keywords, limit=limit
            )
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("get_sitemap", e)

    @mcp.tool()
    async def crawl_site(url: str) -> str:
        """Crawl a site's sitemap to discover pages."""
        try:
            logger.info(f"Tool Call: crawl_site {url}")
            data = await run_in_process(get_sitemap_plain, url)
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("crawl_site", e)

    @mcp.tool()
    async def extract_contacts(url: str) -> str:
        """
        Extract all contact information from a URL.

        Returns structured JSON with emails, phones, socials, and detected names.
        """
        try:
            logger.info(f"Tool Call: extract_contacts {url}")
            data = await run_in_process(get_contacts, url)
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("extract_contacts", e)

    @mcp.tool()
    async def batch_contacts(urls: list[str]) -> str:
        """
        Extract contacts from multiple URLs in parallel.

        Uses hardware-limited concurrency (CPU cores - 1) for optimal performance.
        """
        try:
            logger.info(f"Tool Call: batch_contacts for {len(urls)} URLs")

            # Hardware-limited parallelism
            max_workers = max(1, (os.cpu_count() or 1) - 1)
            semaphore = asyncio.Semaphore(max_workers)

            async def process_url(url: str) -> dict:
                async with semaphore:
                    try:
                        data = await run_in_process(get_contacts, url)
                        return {"url": url, **data}
                    except Exception as e:
                        return {"url": url, "error": str(e)}

            tasks = [process_url(url) for url in urls]
            results = await asyncio.gather(*tasks)

            return create_envelope(
                "success",
                list(results),
                meta={"count": len(results), "workers": max_workers},
            )
        except Exception as e:
            return format_error("batch_contacts", e)

    @mcp.tool()
    async def extract_links(
        url: str,
        filter_external: bool = False,
    ) -> str:
        """
        Extract all hyperlinks from a webpage.

        Args:
            url: Target webpage URL
            filter_external: If True, only return internal links (same domain)

        Returns structured JSON with links, internal_count, external_count.
        """
        try:
            logger.info(f"Tool Call: extract_links {url}")
            data = await run_in_process(
                _extract_links, url, filter_external=filter_external
            )
            return create_envelope("success", data, meta={"url": url})
        except Exception as e:
            return format_error("extract_links", e)

    @mcp.tool()
    async def search_web(query: str) -> str:
        """Perform a web search and return results."""
        try:
            logger.info(f"Tool Call: search_web '{query}'")
            data = await run_in_process(perform_search, query)
            return create_envelope("success", data, meta={"query": query})
        except Exception as e:
            return format_error("search_web", e)

    @mcp.tool()
    async def deep_research(query: str) -> str:
        """Perform Deep Research (Search + Crawl + Report)."""
        try:
            logger.info(f"Tool Call: deep_research for '{query}'")
            data = await run_in_process(perform_deep_research, query)
            return create_envelope("success", data, meta={"query": query})
        except Exception as e:
            return format_error("deep_research", e)

    logger.info("Registered: discovery tools (7)")
