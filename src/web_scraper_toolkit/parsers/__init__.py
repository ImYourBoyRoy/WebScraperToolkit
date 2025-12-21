# ./src/web_scraper_toolkit/parsers/__init__.py
"""
Parsers Package
===============

Exports key parser utilities, extraction, search, and sitemap functions.

Sub-packages:
    - extraction: Contact, metadata, media extraction
    - search: Web search and SERP parsing
    - sitemap: Sitemap discovery and parsing
"""

from .html_to_markdown import MarkdownConverter
from .sitemap import (
    fetch_sitemap_content as fetch_sitemap,
    parse_sitemap_urls as parse_sitemap,
    extract_sitemap_tree,
)
from .scraping_tools import read_website_markdown, read_website_content

# Re-exports from extraction sub-package (backward compatibility)
from .extraction.contacts import extract_emails, extract_phones, extract_socials
from .extraction.metadata import extract_metadata
from .extraction.media import capture_screenshot, save_as_pdf

# Re-exports from search sub-package
from .search.search import general_web_search, deep_research_with_google
from .search.serp_parser import SerpParser

__all__ = [
    # Core
    "MarkdownConverter",
    "read_website_markdown",
    "read_website_content",
    # Sitemap
    "fetch_sitemap",
    "parse_sitemap",
    "extract_sitemap_tree",
    # Extraction
    "extract_emails",
    "extract_phones",
    "extract_socials",
    "extract_metadata",
    "capture_screenshot",
    "save_as_pdf",
    # Search
    "general_web_search",
    "deep_research_with_google",
    "SerpParser",
]
