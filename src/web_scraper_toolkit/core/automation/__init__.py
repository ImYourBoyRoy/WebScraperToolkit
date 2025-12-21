# ./src/web_scraper_toolkit/core/automation/__init__.py
"""
Automation Sub-Package
======================

Form filling, retry logic, and utility functions.
"""

from .forms import fill_form, extract_tables, click_element
from .utilities import health_check, validate_url, detect_content_type, download_file
from .retry import RetryConfig, with_retry, retry_operation, update_retry_config

__all__ = [
    # Forms
    "fill_form",
    "extract_tables",
    "click_element",
    # Utilities
    "health_check",
    "validate_url",
    "detect_content_type",
    "download_file",
    # Retry
    "RetryConfig",
    "with_retry",
    "retry_operation",
    "update_retry_config",
]
