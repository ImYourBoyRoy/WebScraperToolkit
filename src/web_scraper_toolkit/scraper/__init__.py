# ./src/web_scraper_toolkit/scraper/__init__.py
"""
Scraper Module
==============

Contains the actual fetching engines (aiohttp, etc).
Separated from the Proxie (Manager) module.
"""

from .aiohttp import ProxyScraper

__all__ = ["ProxyScraper"]
