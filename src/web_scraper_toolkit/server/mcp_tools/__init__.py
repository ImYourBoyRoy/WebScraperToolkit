# ./src/web_scraper_toolkit/server/mcp_tools/__init__.py
"""
MCP Tools Package
=================

Modular MCP tool implementations organized by category.
Each submodule registers tools with the shared MCP server instance.

Categories:
    - scraping: Core scraping tools
    - discovery: Sitemap and contact discovery
    - forms: Form automation and table extraction
    - content: Chunking, tokens, text processing
    - management: Cache, session, history, config
    - diagnostics: Script-backed browser and anti-bot diagnostics
"""

from .scraping import register_scraping_tools
from .discovery import register_discovery_tools
from .forms import register_form_tools
from .content import register_content_tools
from .management import register_management_tools
from .browser_interactive import register_browser_interactive_tools
from .diagnostics import register_diagnostics_tools

__all__ = [
    "register_scraping_tools",
    "register_discovery_tools",
    "register_form_tools",
    "register_content_tools",
    "register_management_tools",
    "register_browser_interactive_tools",
    "register_diagnostics_tools",
]
