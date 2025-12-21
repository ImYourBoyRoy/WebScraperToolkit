# ./src/web_scraper_toolkit/parsers/sitemap/fetching.py
"""
Sitemap Fetching
================

Logic for downloading and recursively walking sitemaps.
"""

import asyncio
import logging
import re
import requests
from typing import List, Optional, Dict, Any

from .parsing import parse_sitemap_urls
from ...core.user_agents import get_simple_headers

logger = logging.getLogger(__name__)


async def fetch_sitemap_content(url: str, manager=None) -> Optional[str]:
    """
    Fetch sitemap content from valid URL.
    Tries requests first, falls back to Playwright for JS/Cloudflare.
    If 'manager' (PlaywrightManager) is provided, it is reused for efficiency.
    """
    # 1. Try Requests with stealth headers
    try:
        headers = get_simple_headers()
        # Run sync request in thread to avoid blocking
        resp = await asyncio.to_thread(requests.get, url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(
            f"Simple sitemap fetch failed for {url} ({e}). Falling back to Playwright..."
        )

    # 2. Playwright Fallback
    try:
        # Lazy import to avoid circular dependency issues at module level if any
        from ...browser.playwright_handler import PlaywrightManager

        should_close = False
        if not manager:
            manager = PlaywrightManager(config={"scraper_settings": {"headless": True}})
            should_close = True

        try:
            # Ensure started (idempotent)
            await manager.start()

            content, _, status = await manager.smart_fetch(url)
            if status == 200:
                return content
            else:
                logger.error(f"Playwright sitemap fetch failed: {status}")
                return None
        finally:
            if should_close:
                await manager.stop()

    except Exception as pe:
        logger.error(f"Failed to fetch sitemap via Playwright: {pe}")
        return None


async def extract_sitemap_tree(
    input_source: str, depth: int = 0, semaphore: asyncio.Semaphore = None, manager=None
) -> List[str]:
    """
    Recursively extracts all URLs from a sitemap or sitemap index.
    """
    if depth > 3:  # Safety break
        logger.warning(f"Max sitemap depth reached at {input_source}")
        return []

    # Initialize semaphore if this is the root call
    if semaphore is None:
        semaphore = asyncio.Semaphore(4)

    # Initialize Shared Browser Manager if root and not provided
    local_manager_created = False
    if depth == 0 and manager is None:
        try:
            from ...browser.playwright_handler import PlaywrightManager

            manager = PlaywrightManager(config={"scraper_settings": {"headless": True}})
            # We don't start it yet - let fetch_sitemap_content start it lazily if requests fails
            local_manager_created = True
        except Exception as e:
            logger.warning(f"Could not initialize shared PlaywrightManager: {e}")

    try:
        content = await fetch_sitemap_content(input_source, manager=manager)
        if not content:
            return []

        # 1. Check for nested sitemaps (Sitemap Index)
        # Check for <sitemap> tags which indicate an index
        nested_sitemaps = []

        # Regex for sitemap locs
        raw_sitemap_matches = re.findall(
            r"(?:<|&lt;)sitemap(?:>|&gt;)\s*(?:<|&lt;)loc(?:>|&gt;)(.*?)(?:<|&lt;)/loc(?:>|&gt;)",
            content,
            re.IGNORECASE | re.DOTALL,
        )

        for raw in raw_sitemap_matches:
            url = raw.strip()
            if "<![CDATA[" in url.upper():
                url = re.sub(r"<!\[CDATA\[", "", url, flags=re.IGNORECASE)
                url = re.sub(r"\]\]>", "", url, flags=re.IGNORECASE)
            nested_sitemaps.append(url.strip())

        if nested_sitemaps:
            logger.info(
                f"Found sitemap index at {input_source} with {len(nested_sitemaps)} nested sitemaps."
            )

            async def _recursive_task(url):
                async with semaphore:
                    return await extract_sitemap_tree(
                        url, depth + 1, semaphore=semaphore, manager=manager
                    )

            tasks = [_recursive_task(url) for url in nested_sitemaps]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_urls = []
            for i, res in enumerate(results):
                if isinstance(res, list):
                    if not res:
                        logger.debug(
                            f"Nested sitemap {nested_sitemaps[i]} returned 0 URLs."
                        )
                    all_urls.extend(res)
                else:
                    logger.error(f"Error recursing sitemap {nested_sitemaps[i]}: {res}")

            if not all_urls:
                logger.warning(
                    f"Sitemap Index at {input_source} had {len(nested_sitemaps)} children but yielded 0 URLs. (Possible rate limit or empty sub-sitemaps)"
                )

            return all_urls

        # 2. Extract standard URLs (Leaf Node)
        return parse_sitemap_urls(content)

    finally:
        # If we created a local manager at root, close it
        if local_manager_created and manager:
            await manager.stop()


async def peek_sitemap_index(input_source: str) -> Dict[str, Any]:
    """
    Analyzes a sitemap index without deep recursion.
    Returns:
       {
         'type': 'index' | 'urlset',
         'sitemaps': [{'url': str, 'count': int}, ...],  # If index
         'urls': [str, ...],                             # If urlset
       }
    """
    content = await fetch_sitemap_content(input_source)
    if not content:
        return {"type": "error", "message": "Could not fetch content"}

    # 1. Check for Index
    raw_sitemap_matches = re.findall(
        r"(?:<|&lt;)sitemap(?:>|&gt;)\s*(?:<|&lt;)loc(?:>|&gt;)(.*?)(?:<|&lt;)/loc(?:>|&gt;)",
        content,
        re.IGNORECASE | re.DOTALL,
    )

    nested_sitemaps = []
    for raw in raw_sitemap_matches:
        url = raw.strip()
        if "<![CDATA[" in url.upper():
            url = re.sub(r"<!\[CDATA\[", "", url, flags=re.IGNORECASE)
            url = re.sub(r"\]\]>", "", url, flags=re.IGNORECASE)
        nested_sitemaps.append(url.strip())

    if nested_sitemaps:
        # It IS an index. Let's get "Quick Counts" for each child.
        logger.info(f"Peeking at sitemap index: {len(nested_sitemaps)} children.")

        # Local semaphore for this concurrency task
        local_semaphore = asyncio.Semaphore(4)

        async def _count_urls(url):
            async with local_semaphore:
                c = await fetch_sitemap_content(url)
                if not c:
                    return {"url": url, "count": 0, "error": True}
                # Quick regex count of <loc> or <link>
                count = len(
                    re.findall(r"(?:<|&lt;)(?:[\w]+:)?loc(?:>|&gt;)", c, re.IGNORECASE)
                )
                return {"url": url, "count": count}

        tasks = [_count_urls(u) for u in nested_sitemaps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        sitemap_stats = []
        for res in results:
            if isinstance(res, dict):
                sitemap_stats.append(res)
            else:
                sitemap_stats.append({"url": "error", "count": 0})

        return {"type": "index", "sitemaps": sitemap_stats}

    else:
        # It is a LEAF sitemap (Urlset)
        urls = parse_sitemap_urls(content)
        return {"type": "urlset", "urls": urls}
