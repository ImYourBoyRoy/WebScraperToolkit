# ./src/web_scraper_toolkit/core/state/cache.py
"""
Response Cache
==============

TTL-based caching for scraped content to avoid redundant fetches.
Supports both in-memory and disk persistence.

Usage:
    cache = ResponseCache(config)
    content = cache.get(url)
    if not content:
        content = scrape(url)
        cache.set(url, content)

Key Features:
    - Configurable TTL (time-to-live)
    - Disk persistence for long sessions
    - Memory-first with disk fallback
    - URL normalization for consistent keys
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Any
from urllib.parse import urlparse, urlencode, parse_qs

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Configuration for response cache."""

    enabled: bool = True
    ttl_seconds: int = 300  # 5 minutes default
    directory: str = "./cache"
    max_size_mb: int = 100

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheConfig":
        return cls(
            enabled=data.get("enabled", True),
            ttl_seconds=data.get("ttl_seconds", 300),
            directory=data.get("directory", "./cache"),
            max_size_mb=data.get("max_size_mb", 100),
        )


@dataclass
class CacheEntry:
    """Single cache entry with metadata."""

    content: str
    timestamp: float
    url: str
    content_type: str = "text/html"


class ResponseCache:
    """
    TTL-based response cache with disk persistence.

    Thread-safe for async usage. Uses URL hash as cache key.
    """

    def __init__(self, config: Optional[CacheConfig] = None):
        self.config = config or CacheConfig()
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0

        # Ensure cache directory exists
        if self.config.enabled:
            Path(self.config.directory).mkdir(parents=True, exist_ok=True)

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent caching."""
        parsed = urlparse(url)
        # Sort query params for consistency
        query = urlencode(
            sorted(parse_qs(parsed.query, keep_blank_values=True).items())
        )
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if query:
            normalized += f"?{query}"
        return normalized.lower().rstrip("/")

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        normalized = self._normalize_url(url)
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def _get_disk_path(self, key: str) -> Path:
        """Get disk cache file path."""
        return Path(self.config.directory) / f"{key}.json"

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry has expired."""
        return (time.time() - entry.timestamp) > self.config.ttl_seconds

    def get(self, url: str) -> Optional[str]:
        """
        Get cached content for URL.

        Returns None if not cached or expired.
        """
        if not self.config.enabled:
            return None

        key = self._get_cache_key(url)

        # 1. Check memory cache
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if not self._is_expired(entry):
                self._hits += 1
                logger.debug(f"Cache HIT (memory): {url[:50]}...")
                return entry.content
            else:
                # Expired, remove from memory
                del self._memory_cache[key]

        # 2. Check disk cache
        disk_path = self._get_disk_path(key)
        if disk_path.exists():
            try:
                with open(disk_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entry = CacheEntry(
                        content=data["content"],
                        timestamp=data["timestamp"],
                        url=data["url"],
                        content_type=data.get("content_type", "text/html"),
                    )
                    if not self._is_expired(entry):
                        # Promote to memory cache
                        self._memory_cache[key] = entry
                        self._hits += 1
                        logger.debug(f"Cache HIT (disk): {url[:50]}...")
                        return entry.content
                    else:
                        # Expired, delete from disk
                        disk_path.unlink()
            except Exception as e:
                logger.warning(f"Failed to read disk cache: {e}")

        self._misses += 1
        logger.debug(f"Cache MISS: {url[:50]}...")
        return None

    def set(self, url: str, content: str, content_type: str = "text/html") -> None:
        """
        Cache content for URL.

        Stores in both memory and disk for persistence.
        """
        if not self.config.enabled:
            return

        key = self._get_cache_key(url)
        entry = CacheEntry(
            content=content,
            timestamp=time.time(),
            url=url,
            content_type=content_type,
        )

        # 1. Store in memory
        self._memory_cache[key] = entry

        # 2. Store on disk
        try:
            disk_path = self._get_disk_path(key)
            with open(disk_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "content": content,
                        "timestamp": entry.timestamp,
                        "url": url,
                        "content_type": content_type,
                    },
                    f,
                )
            logger.debug(f"Cached: {url[:50]}...")
        except Exception as e:
            logger.warning(f"Failed to write disk cache: {e}")

    def clear(self) -> dict:
        """
        Clear all cache (memory and disk).

        Returns stats about cleared entries.
        """
        memory_count = len(self._memory_cache)
        disk_count = 0

        # Clear memory
        self._memory_cache.clear()

        # Clear disk
        cache_dir = Path(self.config.directory)
        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                try:
                    f.unlink()
                    disk_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cache file {f}: {e}")

        # Reset stats
        self._hits = 0
        self._misses = 0

        logger.info(f"Cache cleared: {memory_count} memory, {disk_count} disk entries")
        return {
            "cleared_memory": memory_count,
            "cleared_disk": disk_count,
        }

    def get_stats(self) -> dict:
        """Get cache statistics."""
        cache_dir = Path(self.config.directory)
        disk_size = 0
        disk_count = 0

        if cache_dir.exists():
            for f in cache_dir.glob("*.json"):
                disk_size += f.stat().st_size
                disk_count += 1

        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "enabled": self.config.enabled,
            "ttl_seconds": self.config.ttl_seconds,
            "memory_entries": len(self._memory_cache),
            "disk_entries": disk_count,
            "disk_size_mb": round(disk_size / 1024 / 1024, 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_percent": round(hit_rate, 1),
        }


# Global cache instance (initialized lazily)
_global_cache: Optional[ResponseCache] = None


def get_cache(config: Optional[CacheConfig] = None) -> ResponseCache:
    """Get or create global cache instance."""
    global _global_cache
    if _global_cache is None:
        _global_cache = ResponseCache(config)
    return _global_cache


def clear_global_cache() -> dict:
    """Clear the global cache."""
    global _global_cache
    if _global_cache:
        return _global_cache.clear()
    return {"cleared_memory": 0, "cleared_disk": 0}
