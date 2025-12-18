# ./src/web_scraper_toolkit/parsers/discovery.py
"""
Smart Discovery Module
======================

Implements intelligent URL discovery by recursively parsing sitemaps and filtering
URLs based on relevance keywords.

Usage:
    from web_scraper_toolkit.parsers.discovery import smart_discover_urls
    results = await smart_discover_urls("https://example.com")

Key Functions:
    - smart_discover_urls: Main entry point for discovery logic.

Dependencies:
    - web_scraper_toolkit.parsers.sitemap_handler
"""

from typing import List, Dict, Any, Optional
import logging

from .sitemap_handler import find_sitemap_urls, peek_sitemap_index, extract_sitemap_tree

logger = logging.getLogger(__name__)

# Default Keywords
DEFAULT_PRIORITY_KEYWORDS = [
    "page",
    "post",
    "main",
    "content",
    "about",
    "team",
    "contact",
    "company",
    "career",
]
DEFAULT_EXCLUDE_KEYWORDS = [
    "product",
    "course",
    "lesson",
    "topic",
    "tag",
    "category",
    "author",
    "archive",
    "feed",
]
DEFAULT_CONTEXT_KEYWORDS = [
    "about",
    "team",
    "leader",
    "contact",
    "career",
    "job",
    "management",
    "investor",
    "press",
]


async def smart_discover_urls(
    homepage: str,
    max_priority: int = 15,
    max_general: int = 20,
    priority_keywords: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    context_keywords: Optional[List[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Intelligently discovers relevant URLs from a homepage by:
    1. Finding sitemaps (standard + heuristic).
    2. Peeking at indices to filter out noise (products, tags).
    3. Extracting URLs from remaining 'content' sitemaps.
    4. Categorizing final URLs into 'high_priority' and 'general'.

    Args:
        homepage: The URL of the site to discover.
        max_priority: Max number of priority URLs to return.
        max_general: Max number of general URLs to return.
        priority_keywords: List of keywords to identify useful content.
        exclude_keywords: List of keywords to skip sitemaps/URLs.
        context_keywords: List of keywords for high-priority classification.

    Returns:
        Dict with keys: 'priority_urls', 'general_urls'
    """
    logger.info(f"[SmartDiscover] Starting discovery for: {homepage}")

    # Use defaults if not provided
    p_keywords = priority_keywords or DEFAULT_PRIORITY_KEYWORDS
    e_keywords = exclude_keywords or DEFAULT_EXCLUDE_KEYWORDS
    c_keywords = context_keywords or DEFAULT_CONTEXT_KEYWORDS

    # 1. Discover Sitemaps
    sitemaps = await find_sitemap_urls(homepage)
    if not sitemaps:
        logger.info("[SmartDiscover] No sitemaps found.")
        return {"priority_urls": [], "general_urls": []}

    all_urls = []

    for sm in sitemaps:
        # 2. Peek at structure
        info = await peek_sitemap_index(sm)

        if info["type"] == "urlset":
            # It's a direct list of URLs
            all_urls.extend(info["urls"])

        elif info["type"] == "index":
            # 3. Filter Children
            for child in info["sitemaps"]:
                c_url = child["url"]
                c_lower = c_url.lower()

                # Exclusion Check
                if any(k in c_lower for k in e_keywords):
                    continue

                # Extract child sitemap
                child_urls = await extract_sitemap_tree(c_url, depth=1)
                all_urls.extend(child_urls)

    # Deduplicate
    unique_urls = list(set(all_urls))
    logger.info(f"[SmartDiscover] Found {len(unique_urls)} total unique URLs.")

    # 4. Prioritize
    priority_final = []
    general_final = []

    for u in unique_urls:
        u_lower = u.lower()
        if any(k in u_lower for k in c_keywords) or any(
            k in u_lower for k in p_keywords
        ):
            priority_final.append(u)
        else:
            general_final.append(u)

    # Truncate
    p_results = priority_final[:max_priority]
    g_results = general_final[:max_general]

    return {
        "priority_urls": [
            {"url": u, "score": 1, "type": "priority"} for u in p_results
        ],
        "general_urls": [
            {"url": u, "score": 0.5, "type": "general"} for u in g_results
        ],
    }
