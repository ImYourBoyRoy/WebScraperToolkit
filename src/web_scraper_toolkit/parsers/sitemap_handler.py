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
import os
import re
from typing import List, Optional
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


async def fetch_sitemap_content(url: str) -> Optional[str]:
    """
    Fetch sitemap content from valid URL.
    Tries requests first, falls back to Playwright for JS/Cloudflare.
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

        manager = PlaywrightManager(config={"scraper_settings": {"headless": True}})
        # We need to start/stop the manager properly.
        # Ideally, we should pass an existing manager if available, but for now we create one.
        await manager.start()
        try:
            content, _, status = await manager.smart_fetch(url)
            if status == 200:
                return content
            else:
                logger.error(f"Playwright sitemap fetch failed: {status}")
                return None
        finally:
            await manager.stop()

    except Exception as pe:
        logger.error(f"Failed to fetch sitemap via Playwright: {pe}")
        return None


def parse_sitemap_urls(content: str) -> List[str]:
    """
    Extract URLs from sitemap XML using robust regex.
    Handles standard <loc> tags.
    """
    # Simple regex for ANY <loc>
    found_urls = re.findall(
        r"(?:<|&lt;)loc(?:>|&gt;)(.*?)(?:<|&lt;)/loc(?:>|&gt;)", content, re.IGNORECASE
    )
    return [u.strip() for u in found_urls if u.strip()]


async def extract_sitemap_tree(input_source: str, depth: int = 0) -> List[str]:
    """
    Fetch/Read and parse a sitemap (local or remote).
    Recursively follows sitemap indices.
    Returns list of PAGE URLs (ignoring nested sitemap URLs in the final output,
    but traversing them).
    """
    if depth > 3:  # prevent infinite recursion
        logger.warning(f"Sitemap recursion depth limit reached at {input_source}")
        return []

    if os.path.exists(input_source):
        # Local file
        try:
            with open(input_source, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read local sitemap: {e}")
            return []
    else:
        # Remote URL
        content = await fetch_sitemap_content(input_source)

    if not content:
        return []

    # Try to determine if it is a Sitemap Index or a URL Set
    # Regex is fast and robust against bad XML

    # 1. Extract all URLs
    all_locs = parse_sitemap_urls(content)
    if not all_locs:
        # Check if content looks like XML but matched nothing
        safe_prev = content[:200].replace("\n", " ")
        logger.warning(
            f"No URLs found in sitemap content {input_source}. Header: {safe_prev}"
        )
        return []

    page_urls = []
    nested_sitemaps = []

    # 2. Heuristic to classify URLs
    # If a sitemap contains links to .xml or .xml.gz, it's likely a sitemap index
    # Standard sitemap spec says <sitemapindex> -> <sitemap> -> <loc>
    # while <urlset> -> <url> -> <loc>
    # But regex loses that context.

    # We will assume if "sitemap" is in the URL or it ends with .xml/.gz, it's a nested sitemap
    # UNLESS it is significantly different.
    # To be safer, let's look for <sitemapindex> tag in content to decide mode.

    is_index = (
        "<sitemapindex" in content.lower() or "&lt;sitemapindex" in content.lower()
    )

    if is_index:
        nested_sitemaps.extend(all_locs)
    else:
        # It's probably a urlset.
        # However, sometimes mixed? unlikely.
        page_urls.extend(all_locs)

    # 3. Recurse if index
    if nested_sitemaps:
        logger.info(
            f"Found sitemap index at {input_source} with {len(nested_sitemaps)} nested sitemaps."
        )
        tasks = [extract_sitemap_tree(url, depth + 1) for url in nested_sitemaps]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for res in results:
            if isinstance(res, list):
                page_urls.extend(res)
            else:
                logger.debug(f"Error recursing sitemap: {res}")

    return page_urls


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
