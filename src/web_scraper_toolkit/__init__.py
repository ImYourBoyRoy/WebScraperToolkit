# ./src/web_scraper_toolkit/__init__.py
"""
Web Scraper Toolkit
===================

Root package exposing the unified API for the toolkit.
Aggregates components from core, browser, and parsers sub-packages.

Usage:
    from src.web_scraper_toolkit import WebCrawler, ScraperConfig

"""

__version__ = "0.1.2"

from .core.config import ScraperConfig, ScraperSettings
from .core.logger import setup_logger
from .core.diagnostics import verify_environment, print_diagnostics
from .browser.playwright_handler import PlaywrightManager
from .browser.crawler import WebCrawler, load_urls_from_source
from .parsers.html_to_markdown import MarkdownConverter
from .parsers.sitemap_handler import (
    fetch_sitemap_content as fetch_sitemap,
    parse_sitemap_urls as parse_sitemap,
    extract_sitemap_tree,
)
from .parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    clean_text,
    capture_screenshot,
    save_as_pdf,
    extract_metadata,
)

__all__ = [
    "ScraperConfig",
    "ScraperSettings",
    "setup_logger",
    "verify_environment",
    "print_diagnostics",
    "PlaywrightManager",
    "WebCrawler",
    "load_urls_from_source",
    "MarkdownConverter",
    "fetch_sitemap",
    "parse_sitemap",
    "extract_sitemap_tree",
    "read_website_markdown",
    "read_website_content",
    "clean_text",
    "capture_screenshot",
    "save_as_pdf",
    "extract_metadata",
]
