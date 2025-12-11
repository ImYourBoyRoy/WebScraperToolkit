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

import re
import logging
import requests
import asyncio
from typing import List, Optional
# Moved PlaywrightManager import to function scope to avoid circular dependency

logger = logging.getLogger(__name__)

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
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logger.warning(f"Simple sitemap fetch failed ({e}). Falling back to Playwright...")

    # 2. Playwright Fallback
    try:
        from ..browser.playwright_handler import PlaywrightManager
        manager = PlaywrightManager(config={"scraper_settings": {"headless": True}})
        async with manager:
            # Manually handle page to get raw response text
            context = await manager.browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            response = await page.goto(url, wait_until="domcontentloaded")
            if response and response.status == 200:
                return await response.text()
            else:
                logger.error(f"Playwright sitemap fetch failed: {response.status if response else 'Unknown'}")
                return None
    except Exception as pe:
        logger.error(f"Failed to fetch sitemap via Playwright: {pe}")
        return None

def parse_sitemap_urls(content: str) -> List[str]:
    """
    Extract URLs from sitemap XML using robust regex.
    Handles standard <loc> tags and browser-rendered &lt;loc&gt; tags.
    """
    urls = []
    # Regex handles <loc>...</loc> AND &lt;loc&gt;...&lt;/loc&gt; from browser view-source
    found_urls = re.findall(r'(?:<|&lt;)loc(?:>|&gt;)(.*?)(?:<|&lt;)/loc(?:>|&gt;)', content)
    
    for u in found_urls:
        clean_u = u.strip()
        if clean_u:
            urls.append(clean_u)
            
    return urls

import os

async def extract_sitemap_tree(input_source: str) -> List[str]:
    """
    Fetch/Read and parse a sitemap (local or remote).
    Returns list of URLs found.
    """
    if os.path.exists(input_source):
        # Local file
        try:
            with open(input_source, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read local sitemap: {e}")
            return []
    else:
        # Remote URL
        content = await fetch_sitemap_content(input_source)
        
    if not content:
        return []
    
    urls = parse_sitemap_urls(content)
    if not urls:
        # Check if content looks like XML but matched nothing
        safe_prev = content[:200].replace('\n', ' ')
        logger.warning(f"No URLs found in sitemap content. Header: {safe_prev}")
        
    return urls
