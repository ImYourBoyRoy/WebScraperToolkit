# ./src/web_scraper_toolkit/parsers/extraction/metadata.py
"""
Metadata Extraction Tools
=========================

Tools for extracting semantic metadata (JSON-LD, OpenGraph, Twitter Cards) from websites.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Union

from bs4 import BeautifulSoup
from ..config import ParserConfig
from ...browser.config import BrowserConfig

logger = logging.getLogger(__name__)


async def _arun_extract_metadata(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
) -> str:
    from ...browser.playwright_handler import PlaywrightManager

    # Config handling
    browser_cfg = BrowserConfig()  # default
    if isinstance(config, BrowserConfig):
        browser_cfg = config
    elif isinstance(config, dict):
        browser_cfg = BrowserConfig(
            headless=config.get("headless", True),
            browser_type=config.get("browser_type", "chromium"),
        )

    manager = PlaywrightManager(config=browser_cfg)
    await manager.start()
    try:
        content, final_url, status = await manager.smart_fetch(url=website_url)
        if status != 200 or not content:
            return f"Error: Could not retrieve content from {website_url}"

        soup = BeautifulSoup(content, "lxml")
        output = f"=== METADATA REPORT: {final_url} ===\n\n"

        # 1. JSON-LD (The Gold Mine)
        json_lds = soup.find_all("script", type="application/ld+json")
        if json_lds:
            output += "## JSON-LD Structures found:\n"
            for i, script in enumerate(json_lds):
                try:
                    # Basic cleaning of script text
                    data = script.string
                    if data:
                        output += f"--- JSON-LD #{i + 1} ---\n{data.strip()}\n\n"
                except Exception:
                    pass
        else:
            output += "## No JSON-LD found.\n\n"

        # 2. Meta Tags (OpenGraph / Twitter)
        output += "## Meta Tags:\n"
        path_metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                if any(
                    x in name
                    for x in ["og:", "twitter:", "description", "keywords", "author"]
                ):
                    path_metadata[name] = content

        for k, v in path_metadata.items():
            output += f"- {k}: {v}\n"

        return output
    finally:
        await manager.stop()


def extract_metadata(
    website_url: str,
    config: Optional[Union[Dict[str, Any], ParserConfig, BrowserConfig]] = None,
) -> str:
    """
    Extracts semantic metadata (JSON-LD, OpenGraph, Twitter Cards) from a URL.
    This provides highly structured data often missed by text scrapers.
    """
    config = config or {}
    try:
        # We use sync wrapper pattern matching other tools
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # We need a native async implementation if called from async context,
            # but for now we reuse the pattern:
            future = asyncio.run_coroutine_threadsafe(
                _arun_extract_metadata(website_url, config), loop
            )
            return future.result()
        else:
            return asyncio.run(_arun_extract_metadata(website_url, config))
    except RuntimeError:
        return asyncio.run(_arun_extract_metadata(website_url, config))
