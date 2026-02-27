# ./src/web_scraper_toolkit/server/handlers/extraction.py
"""
Implement MCP-facing extraction handlers for sitemap and contact workflows.
Used by discovery MCP tools to power sitemap discovery and contact extraction actions.
Run: Imported by server tool registration modules; not executed directly.
Inputs: URL targets, optional keyword filters, and result limits.
Outputs: Structured dictionaries for sitemap/contact results.
Side effects: Performs network access and HTML parsing on target pages.
Operational notes: Contact extraction uses parser-level normalization helpers.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from ...parsers.scraping_tools import (
    read_website_content,
    get_sitemap_urls,
)
from ...parsers.discovery import smart_discover_urls
from ...parsers.extraction.contacts import (
    extract_emails,
    extract_phones,
    extract_socials,
    extract_heuristic_names,
)
from ...parsers.config import ParserConfig

GLOBAL_PARSER_CONFIG = ParserConfig()


async def discover_sitemap(
    url: str, keywords: str | None = None, limit: int = 50
) -> dict[str, object]:
    """Smartly discovers URLs from a sitemap."""
    priority_kw = [k.strip() for k in keywords.split(",")] if keywords else None

    result = await smart_discover_urls(
        url,
        max_priority=limit,
        max_general=limit,
        priority_keywords=priority_kw,
    )

    priority = [item["url"] for item in result.get("priority_urls", [])]
    general = [item["url"] for item in result.get("general_urls", [])]

    combined = priority + general
    combined = combined[:limit]

    return {
        "total_found": len(combined),
        "priority_urls": priority,
        "other_urls": general[: max(0, limit - len(priority))],
        "combined_urls": combined,
    }


async def get_sitemap_plain(url: str) -> str:
    """Legacy sitemap fetching."""
    return get_sitemap_urls(url)


async def get_contacts(url: str) -> dict[str, object]:
    """Extracts contact info from a URL."""
    html_content = read_website_content(url, config=GLOBAL_PARSER_CONFIG)
    if not html_content:
        return {"error": "Failed to retrieve content"}

    soup = BeautifulSoup(html_content, "lxml")
    text = soup.get_text(separator=" ", strip=True)

    emails = extract_emails(html_content, url)
    phones = extract_phones(text, url)
    socials = extract_socials(soup, url)
    names = extract_heuristic_names(soup)

    return {
        "emails": emails,
        "phones": phones,
        "socials": socials,
        "names": names or None,
    }
