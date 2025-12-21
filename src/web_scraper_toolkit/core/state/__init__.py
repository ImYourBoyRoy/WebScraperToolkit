# ./src/web_scraper_toolkit/core/state/__init__.py
"""
State Management Sub-Package
============================

Handles caching, session management, and history tracking.
"""

from .cache import ResponseCache, CacheConfig, get_cache, clear_global_cache
from .session import SessionManager, SessionConfig, get_session_manager
from .history import HistoryManager, HistoryEntry, HistoryConfig, get_history_manager

__all__ = [
    # Cache
    "ResponseCache",
    "CacheConfig",
    "get_cache",
    "clear_global_cache",
    # Session
    "SessionManager",
    "SessionConfig",
    "get_session_manager",
    # History
    "HistoryManager",
    "HistoryEntry",
    "HistoryConfig",
    "get_history_manager",
]
