# ./src/web_scraper_toolkit/server/mcp_tools/_management/__init__.py
"""
Private registration helpers for management MCP tools.
Used by server.mcp_tools.management facade to keep public API stable.
Run: imported by management module during MCP server startup.
Inputs: shared registration context with envelope/error/runtime callbacks.
Outputs: decorated MCP tool functions attached to the provided MCP instance.
Side effects: registers tool handlers on the MCP server object.
Operational notes: private package, not a public import surface.
"""

from .config_tools import register_config_tools
from .job_tools import register_job_tools
from .state_tools import register_state_tools

__all__ = ["register_config_tools", "register_state_tools", "register_job_tools"]
