# ./src/web_scraper_toolkit/parsers/extraction/links.py
"""
Link Extraction
===============

Extracts all hyperlinks from HTML content with filtering and categorization.
Used by MCP `extract_links` tool and available as a core library function.

Usage:
    links = await extract_links("https://example.com")
    # Returns: {"url": "...", "links": [...], "internal_count": 10, ...}

Key Features:
    - Filters internal vs external links
    - Removes duplicates
    - Handles relative URLs
    - Optional fragment filtering
"""

import logging
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ...browser.playwright_handler import PlaywrightManager
from ...browser.config import BrowserConfig

logger = logging.getLogger(__name__)


async def extract_links(
    url: str,
    filter_external: bool = False,
    include_fragments: bool = False,
    config: Optional[BrowserConfig] = None,
) -> Dict[str, Any]:
    """
    Extract all hyperlinks from a webpage.

    Args:
        url: Target webpage URL
        filter_external: If True, only return internal links (same domain)
        include_fragments: If True, include fragment-only links (#section)
        config: Optional browser config

    Returns:
        Dictionary with:
            - url: Source URL
            - links: List of extracted URLs
            - internal_count: Number of internal links
            - external_count: Number of external links
            - total_count: Total unique links found
    """
    logger.info(f"Extracting links from: {url}")

    # Fetch page content
    manager = PlaywrightManager(config or BrowserConfig(headless=True))

    try:
        await manager.start()
        content, final_url, status = await manager.smart_fetch(url)

        if not content:
            return {
                "url": url,
                "links": [],
                "internal_count": 0,
                "external_count": 0,
                "total_count": 0,
                "error": f"Failed to fetch page (status: {status})",
            }

        # Parse links
        links_data = extract_links_from_html(
            content,
            base_url=final_url,
            filter_external=filter_external,
            include_fragments=include_fragments,
        )

        links_data["url"] = final_url
        links_data["status"] = status

        logger.info(f"Extracted {links_data['total_count']} links from {final_url}")
        return links_data

    finally:
        await manager.stop()


def extract_links_from_html(
    html: str,
    base_url: str,
    filter_external: bool = False,
    include_fragments: bool = False,
) -> Dict[str, Any]:
    """
    Extract links from raw HTML content.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links
        filter_external: If True, only return internal links
        include_fragments: If True, include fragment-only links

    Returns:
        Dictionary with link data
    """
    soup = BeautifulSoup(html, "lxml")

    base_domain = urlparse(base_url).netloc.lower()

    internal_links = set()
    external_links = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()

        if not href:
            continue

        # Skip javascript, mailto, tel, etc.
        if href.startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue

        # Handle fragment-only links
        if href.startswith("#"):
            if include_fragments:
                internal_links.add(urljoin(base_url, href))
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)

        # Remove fragment if not included
        if not include_fragments and "#" in full_url:
            full_url = full_url.split("#")[0]

        # Skip empty after cleaning
        if not full_url or full_url == base_url:
            continue

        # Categorize as internal or external
        parsed = urlparse(full_url)
        link_domain = parsed.netloc.lower()

        # Normalize www prefix
        if link_domain.startswith("www."):
            link_domain = link_domain[4:]
        if base_domain.startswith("www."):
            base_domain_clean = base_domain[4:]
        else:
            base_domain_clean = base_domain

        if link_domain == base_domain_clean or link_domain == base_domain:
            internal_links.add(full_url)
        else:
            external_links.add(full_url)

    # Build result
    if filter_external:
        all_links = sorted(internal_links)
    else:
        all_links = sorted(internal_links | external_links)

    return {
        "links": all_links,
        "internal_count": len(internal_links),
        "external_count": len(external_links),
        "total_count": len(all_links),
    }


def extract_links_sync(html: str, base_url: str = "") -> List[str]:
    """
    Synchronous link extraction from HTML (no browser needed).

    Convenience function for when you already have HTML content.

    Args:
        html: Raw HTML content
        base_url: Base URL for resolving relative links

    Returns:
        List of extracted URLs
    """
    result = extract_links_from_html(html, base_url)
    return result["links"]
