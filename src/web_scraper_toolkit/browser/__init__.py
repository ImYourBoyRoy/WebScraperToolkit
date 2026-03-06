# ./src/web_scraper_toolkit/browser/__init__.py
"""
Browser package exports for WebScraperToolkit.

Run via imports (no standalone CLI entrypoint).
Inputs: consumer imports from scraper/parsers integrations.
Outputs: stable public browser API symbols used across the toolkit.
Side effects: none at import time beyond symbol binding.
Operational notes: keep exports backward-compatible for downstream tools.
"""

from .playwright_handler import PlaywrightManager, classify_bot_block, BotBlockReason
from .playwright_crawler import WebCrawler
from .host_profiles import HostProfileStore, normalize_host, sanitize_routing_profile
from .domain_identity import registrable_domain, host_lookup_candidates
from .px_solver import PerimeterXSolver
from .serp_native import (
    build_serp_client_hints,
    is_serp_allowlisted,
    is_serp_blocked,
    sanitize_headless_user_agent,
)
from ..core.input import load_urls_from_source

__all__ = [
    "PlaywrightManager",
    "BotBlockReason",
    "classify_bot_block",
    "HostProfileStore",
    "normalize_host",
    "registrable_domain",
    "host_lookup_candidates",
    "sanitize_routing_profile",
    "PerimeterXSolver",
    "sanitize_headless_user_agent",
    "build_serp_client_hints",
    "is_serp_allowlisted",
    "is_serp_blocked",
    "WebCrawler",
    "load_urls_from_source",
]
