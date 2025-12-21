# ./src/web_scraper_toolkit/core/http_client.py
"""
Shared HTTP Client
==================

Provides a shared aiohttp session with connection pooling for efficient
batch requests. Reduces connection overhead and improves performance
for operations like sitemap fetching and batch scraping.

Usage:
    session = await SharedHttpClient.get_session()
    async with session.get(url) as response:
        content = await response.text()

Key Features:
    - Connection pooling (configurable limit)
    - DNS caching (configurable TTL)
    - Automatic cleanup of closed connections
    - Thread-safe singleton pattern
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class HttpConfig:
    """Configuration for HTTP client connection pooling."""

    connection_pool_limit: int = 100
    connection_per_host: int = 10
    dns_cache_ttl: int = 300  # seconds
    total_timeout: int = 30  # seconds
    connect_timeout: int = 10  # seconds

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HttpConfig":
        return cls(
            connection_pool_limit=data.get("connection_pool_limit", 100),
            connection_per_host=data.get("connection_per_host", 10),
            dns_cache_ttl=data.get("dns_cache_ttl", 300),
            total_timeout=data.get("total_timeout", 30),
            connect_timeout=data.get("connect_timeout", 10),
        )


# Global HTTP config (can be set from config.json)
_http_config: Optional[HttpConfig] = None


def get_http_config() -> HttpConfig:
    """Get global HTTP configuration."""
    global _http_config
    if _http_config is None:
        _http_config = HttpConfig()
    return _http_config


def set_http_config(config: HttpConfig) -> None:
    """Set global HTTP configuration."""
    global _http_config
    _http_config = config


class SharedHttpClient:
    """
    Singleton HTTP client with connection pooling.

    Thread-safe for async usage. Session is created lazily on first request.
    """

    _session: Optional[aiohttp.ClientSession] = None
    _lock: asyncio.Lock = None

    # Default headers
    DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    @classmethod
    async def get_session(
        cls,
        timeout: Optional[aiohttp.ClientTimeout] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> aiohttp.ClientSession:
        """
        Get or create the shared session with connection pooling.

        Args:
            timeout: Optional custom timeout (uses default if not provided)
            headers: Optional additional headers to merge with defaults

        Returns:
            Shared aiohttp ClientSession
        """
        # Initialize lock if needed (thread-safe)
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._session is None or cls._session.closed:
                config = get_http_config()
                connector = aiohttp.TCPConnector(
                    limit=config.connection_pool_limit,
                    limit_per_host=config.connection_per_host,
                    ttl_dns_cache=config.dns_cache_ttl,
                    enable_cleanup_closed=True,
                )

                merged_headers = {**cls.DEFAULT_HEADERS}
                if headers:
                    merged_headers.update(headers)

                default_timeout = aiohttp.ClientTimeout(
                    total=config.total_timeout,
                    connect=config.connect_timeout,
                )

                cls._session = aiohttp.ClientSession(
                    connector=connector,
                    timeout=timeout or default_timeout,
                    headers=merged_headers,
                )
                logger.info(
                    f"SharedHttpClient: Created session (pool={config.connection_pool_limit}, "
                    f"per_host={config.connection_per_host})"
                )

        return cls._session

    @classmethod
    async def close(cls) -> None:
        """
        Close the shared session.

        Call this during application shutdown for clean cleanup.
        """
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
                logger.info("SharedHttpClient: Session closed")
            cls._session = None

    @classmethod
    async def fetch(
        cls,
        url: str,
        method: str = "GET",
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Convenience method for making requests with the shared session.

        Args:
            url: Target URL
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments for aiohttp request

        Returns:
            aiohttp ClientResponse
        """
        session = await cls.get_session()
        return await session.request(method, url, **kwargs)

    @classmethod
    async def get_text(cls, url: str, **kwargs: Any) -> str:
        """
        Fetch URL and return text content.

        Args:
            url: Target URL
            **kwargs: Additional arguments for aiohttp request

        Returns:
            Response text content
        """
        session = await cls.get_session()
        async with session.get(url, **kwargs) as response:
            return await response.text()


# Convenience function for module-level access
async def get_shared_session() -> aiohttp.ClientSession:
    """Get the shared HTTP session."""
    return await SharedHttpClient.get_session()


async def close_shared_session() -> None:
    """Close the shared HTTP session."""
    await SharedHttpClient.close()
