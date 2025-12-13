# ./src/web_scraper_toolkit/parsers/sitemap_handler.py
"""
Sitemap Handler
===============

Logic for extracting and analyzing sitemaps (XML/TXT).
Handles sitemap indices (recursive parsing) and filters for high-value pages.

Usage:
    urls = await extract_sitemap_tree("https://site.com/sitemap.xml")

Key Functions:
    - fetch_sitemap: Downloads raw XML.
    - parse_sitemap: Extracts URLs.
    - extract_sitemap_tree: Recursive traversal.
"""

import asyncio
import logging
import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Common sitemap paths to probe
COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap-index.xml",
    "/sitemap-index.xml.gz",
    "/sitemap.xml.gz",
    "/sitemap-index.html",
    "/sitemap.html",
    "/sitemap.txt",
    "/sitemap_index.txt",
    "/wp-sitemap.xml",
    "/wp-sitemap-index.xml",
    "/news-sitemap.xml",
    "/post-sitemap.xml",
    "/page-sitemap.xml",
    # WordPress specific
    "/wp-sitemap-posts-post-1.xml",
    "/wp-sitemap-posts-page-1.xml",
]


async def fetch_sitemap_content(url: str, manager=None) -> Optional[str]:
    """
    Fetch sitemap content from valid URL.
    Tries requests first, falls back to Playwright for JS/Cloudflare.
    If 'manager' (PlaywrightManager) is provided, it is reused for efficiency.
    """
    # 1. Try Requests
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        }
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
        from ..browser.playwright_handler import PlaywrightManager

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


# Global semaphore to limit concurrent sitemap crawls
# We default to 4 which is safe for most laptops (like the user's 4-cpu one)


def parse_sitemap_urls(content: str) -> List[str]:
    """
    Extract URLs from sitemap XML using robust regex.
    Handles standard <loc> tags and CDATA.
    """
    # Regex to capture content inside <loc>...</loc>, ignoring namespace prefixes
    # and handling potential CDATA usage.
    # Logic:
    # 1. Match <loc> or <ns:loc>
    # 2. Capture nested content
    # 3. Handle closing tag

    # This non-greedy match finds content within loc OR link tags (for RSS sitemaps)
    raw_matches = re.findall(
        r"(?:<|&lt;)(?:[\w]+:)?(?:loc|link)(?:>|&gt;)(.*?)(?:<|&lt;)/(?:[\w]+:)?(?:loc|link)(?:>|&gt;)",
        content,
        re.IGNORECASE | re.DOTALL,
    )

    cleaned_urls = []
    for raw in raw_matches:
        cleaned = raw.strip()

        # Robustly remove CDATA wrapper if present (case insensitive)
        if "<![CDATA[" in cleaned.upper():
            # Use regex for case-insensitive replacement to be safe
            cleaned = re.sub(r"<!\[CDATA\[", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\]\]>", "", cleaned, flags=re.IGNORECASE)

        cleaned_urls.append(cleaned.strip())

    return [u for u in cleaned_urls if u]


# SITEMAP_CONCURRENCY_LIMIT removed. Semaphores are now created per-request to avoid loop binding issues.


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
            from ..browser.playwright_handler import PlaywrightManager

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


# --- New Discovery Logic ---


async def _check_robots_txt(base_url: str) -> List[str]:
    """Parses robots.txt for Sitemap: directives."""
    robots_url = urljoin(base_url, "/robots.txt")
    logger.info(f"Checking {robots_url} for sitemaps...")
    found_sitemaps = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = await asyncio.to_thread(
            requests.get, robots_url, headers=headers, timeout=10
        )
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        found_sitemaps.append(parts[1].strip())
    except Exception as e:
        logger.warning(f"Failed to check robots.txt: {e}")

    return found_sitemaps


async def _check_common_paths(base_url: str) -> List[str]:
    """Probes common sitemap locations."""
    found_sitemaps = []

    async def probe(path: str):
        url = urljoin(base_url, path)
        try:
            # Head request first to save bandwidth
            resp = await asyncio.to_thread(
                requests.head, url, timeout=5, headers={"User-Agent": "Mozilla/5.0"}
            )
            if resp.status_code == 200:
                # Double check content type or perform a GET if HEAD is successful to confirm it's not a soft 404 HTML
                # But for speed, if status is 200, we treat it as candidate.
                # Ideally we check content-type.
                ct = resp.headers.get("Content-Type", "").lower()
                if "xml" in ct or "text" in ct:
                    return url
        except Exception:
            pass
        return None

    tasks = [probe(path) for path in COMMON_SITEMAP_PATHS]
    results = await asyncio.gather(*tasks)

    for res in results:
        if res:
            found_sitemaps.append(res)

    return found_sitemaps


async def _check_homepage_for_sitemap(base_url: str) -> List[str]:
    """Scrapes homepage for <link rel='sitemap'> or footer links."""
    found_sitemaps = []
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = await asyncio.to_thread(
            requests.get, base_url, headers=headers, timeout=10
        )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.content, "lxml")

            # Check <link> tags
            links = soup.find_all("link", rel=re.compile(r"sitemap", re.I))
            for link in links:
                href = link.get("href")
                if href:
                    found_sitemaps.append(urljoin(base_url, href))

            # Check footer/body links by text
            # This is heuristic and might be noisy, so we are strict with text
            sitemap_text_regex = re.compile(r"^(Sitemap|Site Map|XML Sitemap)$", re.I)
            a_tags = soup.find_all("a", string=sitemap_text_regex)
            for a in a_tags:
                href = a.get("href")
                if href:
                    found_sitemaps.append(urljoin(base_url, href))

    except Exception as e:
        logger.warning(f"Failed to check homepage for sitemap links: {e}")

    return found_sitemaps


async def find_sitemap_urls(target_url: str) -> List[str]:
    """
    Comprehensive strategy to find sitemap URLs for a given target URL.
    1. Checks robots.txt
    2. Checks common paths
    3. Checks homepage HTML
    4. Handles duplicates and validates uniqueness
    """
    logger.info(f"Starting robust sitemap discovery for {target_url}")

    # Normalize base URL (e.g. remove path if it's just a subpage, or keep it? usually sitemaps are at root)
    parsed = urlparse(target_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    tasks = [
        _check_robots_txt(base_url),
        _check_common_paths(base_url),
        _check_homepage_for_sitemap(base_url),
    ]

    results = await asyncio.gather(*tasks)

    # Flatten results
    all_candidates = []
    for res_list in results:
        all_candidates.extend(res_list)

    # Deduplicate
    unique_sitemaps = sorted(list(set(all_candidates)))

    logger.info(
        f"Discovered {len(unique_sitemaps)} potential sitemaps: {unique_sitemaps}"
    )

    return unique_sitemaps
