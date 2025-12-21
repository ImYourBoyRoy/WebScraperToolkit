# ./src/web_scraper_toolkit/core/__init__.py
"""
Core Package
============

Core utilities, state management, content processing, and automation.

Sub-packages:
    - state: Cache, session, and history management
    - content: Text chunking and token counting
    - automation: Form filling, retry logic, utilities
"""

# Root level utilities
from .logger import setup_logger
from .file_utils import generate_safe_filename, ensure_directory
from .utils import truncate_text

# Re-exports from state sub-package (backward compatibility)
from .state.cache import ResponseCache, CacheConfig, get_cache, clear_global_cache
from .state.session import SessionManager, SessionConfig, get_session_manager
from .state.history import (
    HistoryManager,
    HistoryEntry,
    HistoryConfig,
    get_history_manager,
)

# Re-exports from content sub-package
from .content.chunking import chunk_content, chunk_content_simple
from .content.tokens import count_tokens, get_token_info, truncate_to_tokens

# Re-exports from automation sub-package
from .automation.forms import fill_form, extract_tables, click_element
from .automation.utilities import (
    health_check,
    validate_url,
    detect_content_type,
    download_file,
)
from .automation.retry import (
    RetryConfig,
    with_retry,
    retry_operation,
    update_retry_config,
)

# HTTP Client with connection pooling
from .http_client import (
    SharedHttpClient,
    HttpConfig,
    get_shared_session,
    close_shared_session,
    get_http_config,
    set_http_config,
)

__all__ = [
    # Logger
    "setup_logger",
    # File utils
    "generate_safe_filename",
    "ensure_directory",
    # Utils
    "truncate_text",
    # State - Cache
    "ResponseCache",
    "CacheConfig",
    "get_cache",
    "clear_global_cache",
    # State - Session
    "SessionManager",
    "SessionConfig",
    "get_session_manager",
    # State - History
    "HistoryManager",
    "HistoryEntry",
    "HistoryConfig",
    "get_history_manager",
    # Content
    "chunk_content",
    "chunk_content_simple",
    "count_tokens",
    "get_token_info",
    "truncate_to_tokens",
    # Automation - Forms
    "fill_form",
    "extract_tables",
    "click_element",
    # Automation - Utilities
    "health_check",
    "validate_url",
    "detect_content_type",
    "download_file",
    # Automation - Retry
    "RetryConfig",
    "with_retry",
    "retry_operation",
    "update_retry_config",
    # HTTP Client
    "SharedHttpClient",
    "HttpConfig",
    "get_shared_session",
    "close_shared_session",
    "get_http_config",
    "set_http_config",
]
