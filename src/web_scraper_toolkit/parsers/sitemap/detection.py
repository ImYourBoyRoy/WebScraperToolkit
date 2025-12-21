# ./src/web_scraper_toolkit/parsers/sitemap/detection.py
"""
Sitemap Detection
=================

Heuristic methods for discovering sitemap URLs.
"""

import asyncio
import logging
import re
import requests
from typing import List
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from .models import COMMON_SITEMAP_PATHS
from ...core.user_agents import get_simple_headers

logger = logging.getLogger(__name__)


async def _check_robots_txt(base_url: str) -> List[str]:
    """Parses robots.txt for Sitemap: directives."""
    robots_url = urljoin(base_url, "/robots.txt")
    logger.info(f"Checking {robots_url} for sitemaps...")
    found_sitemaps = []
    try:
        headers = get_simple_headers()
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
                requests.head, url, timeout=5, headers=get_simple_headers()
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
        headers = get_simple_headers()
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
