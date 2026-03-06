# ./src/web_scraper_toolkit/browser/host_profiles.py
"""
Public host profile API facade with backward-compatible imports.
Run: imported by browser manager, CLI, tests, and MCP handlers.
Inputs: host profile payloads and host identifiers passed by callers.
Outputs: HostProfileStore behavior and routing profile sanitization helpers.
Side effects: delegated HostProfileStore methods read/write JSON profile files.
Operational notes: preserve legacy module path while internals live in _host_profiles.
"""

from __future__ import annotations

from ._host_profiles import HostProfileStore, sanitize_routing_profile
from .domain_identity import normalize_host

__all__ = [
    "HostProfileStore",
    "normalize_host",
    "sanitize_routing_profile",
]
