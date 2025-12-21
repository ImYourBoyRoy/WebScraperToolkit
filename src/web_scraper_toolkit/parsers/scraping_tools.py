# ./src/web_scraper_toolkit/parsers/scraping_tools.py
"""
Scraping Tools Collection
=========================

A suite of high-level tools for specific scraping tasks.
Includes markdown conversion, metadata extraction, and SERP parsing helpers.
Used heavily by the MCP server and CLI.

Usage:
    markdown = read_website_markdown(url)
    results = general_web_search(query)

Key Tools:
    - read_website_markdown: Full page to MD.
    - read_website_content: Raw text.
    - general_web_search: DuckDuckGo interface.

Architecture:
    This module acts as a facade, re-exporting tools from:
    - .search
    - .content
    - .extraction.metadata
    - .extraction.media
"""

import logging

# Re-exporting from specialized modules
from .search.search import (
    general_web_search,
    deep_research_with_google,
    finish_research_for_field,
)
from .content import (
    read_website_content,
    read_website_markdown,
)
from .extraction.metadata import (
    extract_metadata,
)
from .extraction.media import (
    capture_screenshot,
    save_as_pdf,
)

# Relative imports regarding PlaywrightManager moved to function scope to resolve circular dependencies.
# We keep these here if legacy code relies on them being importable from here,
# though ideally they should verify they are used or not.
from .search.serp_parser import SerpParser
from .html_to_markdown import MarkdownConverter
from .sitemap import find_sitemap_urls, extract_sitemap_tree, get_sitemap_urls
from .config import ParserConfig
from ..browser.config import BrowserConfig


logger = logging.getLogger(__name__)

__all__ = [
    "read_website_content",
    "read_website_markdown",
    "extract_metadata",
    "capture_screenshot",
    "save_as_pdf",
    "general_web_search",
    "deep_research_with_google",
    "finish_research_for_field",
    "get_sitemap_urls",
    "SerpParser",
    "MarkdownConverter",
    "find_sitemap_urls",
    "extract_sitemap_tree",
    "ParserConfig",
    "BrowserConfig",
]
