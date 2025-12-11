# ./src/web_scraper_toolkit/server/__init__.py
"""
Server Module
=============

This module exposes the FastMCP server instance for the Web Scraper Toolkit.
It allows the server to be imported and run programmatically or via specific runners.

Usage:
    from src.web_scraper_toolkit.server import mcp
    mcp.run()

Components:
    - mcp: The FastMCP instance configured with scraping tools.
"""

from .mcp_server import mcp

__all__ = ["mcp"]
