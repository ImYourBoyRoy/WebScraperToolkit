# ./src/web_scraper_toolkit/parsers/search/__init__.py
"""
Search Sub-Package
==================

Web search and SERP parsing utilities.
"""

from .search import (
    general_web_search,
    deep_research_with_google,
    finish_research_for_field,
)
from .serp_parser import SerpParser

# Async versions (for direct async usage)
from .search import _arun_search, _arun_deep_research

__all__ = [
    "general_web_search",
    "deep_research_with_google",
    "finish_research_for_field",
    "SerpParser",
    "_arun_search",
    "_arun_deep_research",
]
