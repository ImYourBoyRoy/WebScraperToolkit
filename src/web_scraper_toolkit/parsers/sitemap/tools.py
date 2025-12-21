# ./src/web_scraper_toolkit/parsers/sitemap/tools.py
"""
Sitemap Tools
=============

High-level tools for agents to query sitemaps.
"""

import logging
import re
import asyncio
from typing import Optional

from .detection import find_sitemap_urls
from .fetching import extract_sitemap_tree, peek_sitemap_index

logger = logging.getLogger(__name__)


def get_sitemap_urls(*args, **kwargs) -> str:
    """
    Finds, intelligently filters, and prioritizes URLs from a website's sitemap.
    This version is upgraded to handle sitemap index files (which point to other sitemaps)
    as well as regular sitemaps. It dynamically finds a URL from the input.
    """
    # 1. Parse Arguments intelligently
    target_url = None

    # Check explicit kwarg
    if "url" in kwargs:
        target_url = kwargs["url"]
    # Check first positional arg
    elif args and isinstance(args[0], str) and ("http" in args[0] or "www" in args[0]):
        target_url = args[0]

    # Fallback: Search in all args for robustness (handles unstructured input)
    if not target_url:
        full_input_str = (
            " ".join(map(str, args)) + " " + " ".join(map(str, kwargs.values()))
        )
        url_pattern = re.compile(r'https?://[^\s<>"]+|www\.[^\s<>"]+')
        match = url_pattern.search(full_input_str)
        if match:
            target_url = match.group(0)

    if not target_url:
        return "Error: No valid URL could be found in the input. Please provide a valid URL."

    # --- AGENT-FRIENDLY DISCOVERY LOGIC ---

    async def _async_get_sitemap_urls(
        t_url: str, keywords: Optional[str] = None, limit: int = 50
    ):
        # 1. Discover all potential sitemaps
        sitemap_candidates = await find_sitemap_urls(t_url)

        if not sitemap_candidates:
            return f"No sitemaps found for {t_url}"

        # We usually pick the best candidate (e.g. sitemap.xml or sitemap_index.xml)
        # Prioritize 'sitemap.xml' or 'sitemap_index.xml' if present to capture the Index.
        sitemap_candidates.sort(
            key=lambda x: 0
            if x.endswith("/sitemap.xml") or x.endswith("/sitemap_index.xml")
            else 1
        )

        primary_sitemap = sitemap_candidates[0]

        # RECURSIVE IMPORT handled by facade logic previously, but here we are IN the module.
        # We can call extract_sitemap_tree directly.

        # from .sitemap_handler import peek_sitemap_index  <-- Removed circular import attempt if self-referencing
        pass

        # MODE A: Keyword Search (Deep Search)
        # If keywords are provided, we MUST recurse to find matches.
        if keywords:
            logger.info(
                f"Sitemap Search Mode: '{keywords}' requested. Deep crawling..."
            )
            # We use extract_sitemap_tree which recurses
            all_urls = await extract_sitemap_tree(primary_sitemap)

            # Filter
            matches = [u for u in all_urls if keywords.lower() in u.lower()]
            unique_matches = sorted(list(set(matches)))

            output = f"Sitemap Search Results for '{keywords}' in {primary_sitemap}:\n"
            output += f"Found {len(unique_matches)} matching URLs.\n\n"

            for i, u in enumerate(unique_matches):
                if i >= limit:
                    output += f"\n(Truncated. Showing top {limit} of {len(unique_matches)} matches.)"
                    break
                output += f"{u}\n"

            if not unique_matches:
                output += "No URLs found matching that keyword."

            return output

        # MODE B: Structural Overview (Agent Friendly Default)
        # We use peek_sitemap_index to see if it's an index or a list
        structure = await peek_sitemap_index(primary_sitemap)

        if structure["type"] == "index":
            # It's an index. Return summary.
            sitemaps = structure.get("sitemaps", [])
            total_sub = len(sitemaps)
            total_est_urls = sum(s.get("count", 0) for s in sitemaps)

            output = f"Found Sitemap Index at {primary_sitemap}.\n"
            output += f"contains {total_sub} sub-sitemaps with ~{total_est_urls} total URLs.\n"
            output += "To see specific URLs, run again with 'keywords' parameter or target a specific sub-sitemap below.\n\n"
            output += f"=== Sub-Sitemaps (Showing {min(len(sitemaps), limit)} of {len(sitemaps)}) ===\n"

            for i, sm in enumerate(sitemaps):
                if i >= limit:
                    output += f"... and {len(sitemaps) - limit} more.\n"
                    break
                output += f"- {sm['url']} (~{sm['count']} URLs)\n"

            return output

        else:
            # It's a flat URL list. Return URLs.
            urls = structure.get("urls", [])
            unique_urls = sorted(list(set(urls)))

            # Asset filtering (images, etc)
            ignored_extensions = (
                ".jpg",
                ".jpeg",
                ".png",
                ".gif",
                ".webp",
                ".svg",
                ".ico",
                ".pdf",
                ".css",
                ".js",
                ".json",
                ".xml",
                ".rss",
                ".zip",
                ".gz",
            )
            filtered_urls = [
                u for u in unique_urls if not u.lower().endswith(ignored_extensions)
            ]

            output = f"Found Standard Sitemap at {primary_sitemap}.\n"
            output += f"Contains {len(filtered_urls)} relevant URLs (Showing top {min(len(filtered_urls), limit)}).\n\n"

            for i, u in enumerate(filtered_urls):
                if i >= limit:
                    output += f"\n(Truncated. Use 'limit' parameter to see more of the {len(filtered_urls)} URLs.)"
                    break
                output += f"{u}\n"

            return output

    try:
        # Parse kwargs
        keywords = kwargs.get("keywords")
        limit = kwargs.get("limit", 50)
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 50

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                _async_get_sitemap_urls(target_url, keywords, limit), loop
            )
            return future.result()
        else:
            return asyncio.run(_async_get_sitemap_urls(target_url, keywords, limit))

    except Exception as e:
        return f"Error executing sitemap extraction: {e}"
