# ./src/web_scraper_toolkit/parsers/extraction/metadata.py
"""
Metadata Extraction Tools
=========================

Tools for extracting semantic metadata (JSON-LD, OpenGraph, Twitter Cards) from websites.
"""

import asyncio
import logging
from concurrent.futures import Future
from threading import Thread
from typing import Any, Coroutine, Dict, Optional, TypeVar, Union

from bs4 import BeautifulSoup
from ..config import ParserConfig
from ...browser.config import BrowserConfig

logger = logging.getLogger(__name__)
T = TypeVar("T")


def _coerce_attr_to_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item
        return None
    return str(value)


def _run_coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    """Run coroutine safely from sync call sites."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: Future[T] = Future()

    def _runner() -> None:
        try:
            result.set_result(asyncio.run(coro))
        except Exception as exc:  # pragma: no cover
            result.set_exception(exc)

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    return result.result()


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
        browser_cfg = BrowserConfig.from_dict(config)

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
        path_metadata: Dict[str, str] = {}
        for meta in soup.find_all("meta"):
            name = _coerce_attr_to_str(meta.get("name")) or _coerce_attr_to_str(
                meta.get("property")
            )
            content = _coerce_attr_to_str(meta.get("content"))
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
    return _run_coro_sync(_arun_extract_metadata(website_url, config))
