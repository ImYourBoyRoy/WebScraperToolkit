# ./src/web_scraper_toolkit/core/automation/retry.py
"""
Retry Logic
===========

Exponential backoff and retry configuration for resilient scraping.
Handles transient failures gracefully.

Usage:
    @with_retry(max_attempts=3, initial_delay=1.0)
    async def scrape(url):
        ...

Key Features:
    - Exponential backoff
    - Configurable max attempts
    - Jitter for distributed systems
    - Retry-able exception filtering
"""

import asyncio
import functools
import logging
import random
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, Type, Tuple

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryConfig":
        return cls(
            max_attempts=data.get("max_attempts", 3),
            initial_delay_seconds=data.get("initial_delay_seconds", 1.0),
            max_delay_seconds=data.get("max_delay_seconds", 30.0),
            exponential_base=data.get("exponential_base", 2.0),
            jitter=data.get("jitter", True),
        )


# Global retry config
_global_retry_config: Optional[RetryConfig] = None


def get_retry_config() -> RetryConfig:
    """Get global retry configuration."""
    global _global_retry_config
    if _global_retry_config is None:
        _global_retry_config = RetryConfig()
    return _global_retry_config


def set_retry_config(config: RetryConfig) -> None:
    """Set global retry configuration."""
    global _global_retry_config
    _global_retry_config = config


def update_retry_config(
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
) -> Dict[str, Any]:
    """Update retry configuration."""
    config = get_retry_config()

    if max_attempts is not None:
        config.max_attempts = max_attempts
    if initial_delay is not None:
        config.initial_delay_seconds = initial_delay
    if max_delay is not None:
        config.max_delay_seconds = max_delay

    set_retry_config(config)

    return {
        "max_attempts": config.max_attempts,
        "initial_delay_seconds": config.initial_delay_seconds,
        "max_delay_seconds": config.max_delay_seconds,
        "exponential_base": config.exponential_base,
    }


def calculate_delay(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate delay for retry attempt using exponential backoff."""
    delay = config.initial_delay_seconds * (config.exponential_base**attempt)
    delay = min(delay, config.max_delay_seconds)

    if config.jitter:
        # Add random jitter (±25%)
        jitter_range = delay * 0.25
        delay += random.uniform(-jitter_range, jitter_range)

    return max(0, delay)


def with_retry(
    max_attempts: Optional[int] = None,
    initial_delay: Optional[float] = None,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator for adding retry logic to async functions.

    Args:
        max_attempts: Override max attempts
        initial_delay: Override initial delay
        retryable_exceptions: Tuple of exceptions to retry on

    Usage:
        @with_retry(max_attempts=3)
        async def fetch_data(url):
            ...
    """

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            config = get_retry_config()
            attempts = max_attempts or config.max_attempts

            last_exception = None

            for attempt in range(attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < attempts - 1:
                        wait_time = calculate_delay(attempt, config)
                        logger.warning(
                            f"Attempt {attempt + 1}/{attempts} failed: {e}. "
                            f"Retrying in {wait_time:.1f}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"All {attempts} attempts failed: {e}")

            raise last_exception

        return wrapper

    return decorator


async def retry_operation(
    operation: Callable,
    *args,
    max_attempts: Optional[int] = None,
    **kwargs,
) -> Any:
    """
    Execute an operation with retry logic.

    Args:
        operation: Async callable to execute
        *args: Arguments for operation
        max_attempts: Override max attempts
        **kwargs: Keyword arguments for operation

    Returns:
        Result of successful operation
    """
    config = get_retry_config()
    attempts = max_attempts or config.max_attempts

    last_exception = None

    for attempt in range(attempts):
        try:
            return await operation(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt < attempts - 1:
                wait_time = calculate_delay(attempt, config)
                logger.warning(
                    f"Retry {attempt + 1}/{attempts}: {e}. Waiting {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)

    raise last_exception
