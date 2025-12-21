# ./src/web_scraper_toolkit/parsers/extraction/media.py
"""
Media Tools
===========

Tools for capturing visual representations of websites (Screenshots, PDFs).
"""

import asyncio
import logging
from typing import Optional, Dict, Any, Union

from ..config import ParserConfig
from ...browser.config import BrowserConfig

logger = logging.getLogger(__name__)


async def _arun_screenshot(
    url: str, path: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
):
    # config = config or {} # Unused currently
    from ...browser.playwright_handler import PlaywrightManager

    manager = PlaywrightManager(BrowserConfig())
    await manager.start()
    try:
        await manager.capture_screenshot(url, path, full_page=True)
    finally:
        await manager.stop()


def capture_screenshot(
    website_url: str,
    output_path: str,
    config: Optional[Union[Dict[str, Any], ParserConfig]] = None,
) -> str:
    """Captures a full-page screenshot of the URL."""
    # Simple sync wrapper
    try:
        asyncio.run(_arun_screenshot(website_url, output_path, config))
        return f"Screenshot saved to {output_path}"
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return f"Error: {e}"


async def _arun_pdf(
    url: str, path: str, config: Optional[Union[Dict[str, Any], ParserConfig]] = None
):
    # Force headless for PDF
    b_cfg = BrowserConfig(headless=True)

    from ...browser.playwright_handler import PlaywrightManager

    manager = PlaywrightManager(b_cfg)
    await manager.start()
    try:
        await manager.save_pdf(url, path)
    finally:
        await manager.stop()


def save_as_pdf(
    website_url: str,
    output_path: str,
    config: Optional[Union[Dict[str, Any], ParserConfig]] = None,
) -> str:
    """Saves the URL as a PDF (Headless only)."""
    try:
        asyncio.run(_arun_pdf(website_url, output_path, config))
        return f"PDF saved to {output_path}"
    except Exception as e:
        logger.error(f"PDF failed: {e}")
        return f"Error: {e}"
