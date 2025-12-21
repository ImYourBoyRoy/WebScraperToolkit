# ./src/web_scraper_toolkit/server/tools/search.py
"""
Search Tools
============

Web search and deep research capabilities.
"""

from ...parsers.scraping_tools import (
    general_web_search,
    deep_research_with_google,
)
from ...parsers.config import ParserConfig

GLOBAL_PARSER_CONFIG = ParserConfig()


async def perform_search(query: str) -> str:
    """Performs a web search."""
    return await general_web_search(query, config=GLOBAL_PARSER_CONFIG)


async def perform_deep_research(query: str) -> str:
    """Performs deep research (search + crawl)."""
    return await deep_research_with_google(query, config=GLOBAL_PARSER_CONFIG)
