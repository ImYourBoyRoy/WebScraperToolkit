# ./src/web_scraper_toolkit/parsers/extraction/__init__.py
"""
Extraction Sub-Package
======================

Data extraction utilities for contacts, metadata, media, and links.
"""

from .contacts import (
    extract_emails,
    extract_phones,
    extract_socials,
    extract_heuristic_names,
)
from .metadata import extract_metadata
from .media import capture_screenshot, save_as_pdf
from .links import extract_links, extract_links_from_html, extract_links_sync

__all__ = [
    # Contacts
    "extract_emails",
    "extract_phones",
    "extract_socials",
    "extract_heuristic_names",
    # Metadata
    "extract_metadata",
    # Media
    "capture_screenshot",
    "save_as_pdf",
    # Links
    "extract_links",
    "extract_links_from_html",
    "extract_links_sync",
]
