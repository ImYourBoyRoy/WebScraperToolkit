# ./src/web_scraper_toolkit/__init__.py
"""
Web Scraper Toolkit
===================

Root package exposing the unified API for the toolkit.
Aggregates components from core, browser, and parsers sub-packages.

Usage:
    from src.web_scraper_toolkit import WebCrawler, BrowserConfig

"""

__version__ = "0.1.7"

# Configs (Modular)
from .browser.config import BrowserConfig
from .crawler.config import CrawlerConfig
from .parsers.config import ParserConfig
from .proxie.config import ProxieConfig
from .server.config import ServerConfig
from .core.logger import setup_logger
from .core.diagnostics import verify_environment, print_diagnostics
from .browser.playwright_handler import PlaywrightManager
from .browser.playwright_crawler import WebCrawler
from .core.input import load_urls_from_source
from .crawler.engine import AutonomousCrawler
from .playbook.models import Playbook
from .parsers.html_to_markdown import MarkdownConverter
from .parsers.sitemap import (
    fetch_sitemap_content as fetch_sitemap,
    parse_sitemap_urls as parse_sitemap,
    extract_sitemap_tree,
)
from .parsers.discovery import smart_discover_urls
from .parsers.scraping_tools import (
    read_website_markdown,
    read_website_content,
    capture_screenshot,
    save_as_pdf,
    extract_metadata,
)
from .parsers.extraction.contacts import (
    extract_emails,
    extract_phones,
    extract_socials,
)

__all__ = [
    # Configs
    "BrowserConfig",
    "CrawlerConfig",
    "ParserConfig",
    "ProxieConfig",
    "ServerConfig",
    "setup_logger",
    "verify_environment",
    "print_diagnostics",
    "PlaywrightManager",
    "WebCrawler",
    "AutonomousCrawler",
    "Playbook",
    "load_urls_from_source",
    "MarkdownConverter",
    "fetch_sitemap",
    "parse_sitemap",
    "extract_sitemap_tree",
    "smart_discover_urls",
    "read_website_markdown",
    "read_website_content",
    "capture_screenshot",
    "save_as_pdf",
    "extract_metadata",
    "extract_emails",
    "extract_phones",
    "extract_socials",
]
