# ./src/web_scraper_toolkit/core/__init__.py
"""
Expose core toolkit utilities, runtime helpers, diagnostics wrappers, and state primitives.
Run: import from `web_scraper_toolkit.core` for consolidated access to core package APIs.
Inputs: Python imports and function calls from CLI/server/crawler layers.
Outputs: stable re-exported utilities for logging, state, diagnostics, and helper modules.
Side effects: importing this module loads subpackages and binds public symbols in memory.
Operational notes: maintain explicit exports in `__all__` to prevent accidental API surface growth.
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
from .runtime import (
    TimeoutProfile,
    ConcurrencySettings,
    ServerRuntimeSettings,
    RuntimeSettings,
    load_runtime_settings,
    resolve_worker_count,
)
from .script_diagnostics import (
    ScriptDiagnosticsRunner,
    split_cli_args,
    run_toolkit_route_diagnostic,
    run_challenge_matrix_diagnostic,
    run_bot_check_diagnostic,
    run_browser_info_diagnostic,
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
    # Runtime config
    "TimeoutProfile",
    "ConcurrencySettings",
    "ServerRuntimeSettings",
    "RuntimeSettings",
    "load_runtime_settings",
    "resolve_worker_count",
    # Script diagnostics
    "ScriptDiagnosticsRunner",
    "split_cli_args",
    "run_toolkit_route_diagnostic",
    "run_challenge_matrix_diagnostic",
    "run_bot_check_diagnostic",
    "run_browser_info_diagnostic",
]
