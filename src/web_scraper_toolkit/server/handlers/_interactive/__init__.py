# ./src/web_scraper_toolkit/server/handlers/_interactive/__init__.py
"""
Private helpers for InteractiveSession control-surface actions.
Run: imported by `server.handlers.interactive`; not a standalone entrypoint.
Inputs: Playwright Page objects and normalized control arguments.
Outputs: compact dictionaries describing wait/keyboard/scroll/hover/map outcomes.
Side effects: executes browser interactions against the active page session.
Operational notes: payload sizes are capped to keep MCP/LLM exchanges predictable.
"""

from .controls import (
    run_accessibility_tree,
    run_hover,
    run_interaction_map,
    run_press_key,
    run_scroll,
    run_wait_for,
)

__all__ = [
    "run_accessibility_tree",
    "run_wait_for",
    "run_press_key",
    "run_scroll",
    "run_hover",
    "run_interaction_map",
]
