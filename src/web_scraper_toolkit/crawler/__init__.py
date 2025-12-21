# ./src/web_scraper_toolkit/crawler/__init__.py
"""
Proxie Crawler
==============

The high-performance autonomous crawler.
"""

from .engine import AutonomousCrawler
from .frontier import Frontier
from .politeness import PolitenessManager
from .state import StateManager
from .config import CrawlerConfig

# Alias for backward compatibility / Readme consistency
ProxieCrawler = AutonomousCrawler

__all__ = [
    "AutonomousCrawler",
    "ProxieCrawler",
    "Frontier",
    "PolitenessManager",
    "StateManager",
    "CrawlerConfig",
]
