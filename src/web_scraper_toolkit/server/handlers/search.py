# ./src/web_scraper_toolkit/server/handlers/search.py
"""
Implement MCP-facing search handlers.
Used by `server.mcp_tools.discovery` for regular and deep research search flows.
Run: Imported by MCP tool registration modules; no direct CLI entry point.
Inputs: Search query strings.
Outputs: Text reports from search/deep-research pipelines.
Side effects: Performs outbound web lookups through parser/browser search modules.
Operational notes: Delegates stealth/fallback handling to lower-level search utilities.
"""

from __future__ import annotations

from ...parsers.scraping_tools import (
    general_web_search,
    deep_research_with_google,
)
from .config import GLOBAL_BROWSER_CONFIG


async def perform_search(query: str) -> str:
    """Performs a web search."""
    return general_web_search(query, config=GLOBAL_BROWSER_CONFIG)


async def perform_deep_research(query: str) -> str:
    """Performs deep research (search + crawl)."""
    return deep_research_with_google(query, config=GLOBAL_BROWSER_CONFIG)
