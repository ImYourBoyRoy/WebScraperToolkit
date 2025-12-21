# ./src/web_scraper_toolkit/core/automation/utilities.py
"""
Utility Functions
=================

Helper utilities for URL validation, health checks, and content detection.
Enables agents to pre-flight check URLs before full scraping.

Usage:
    result = await validate_url("https://example.com")
    content_type = await detect_content_type("https://example.com/file.pdf")

Key Features:
    - Fast HEAD requests for pre-flight checks
    - Content type detection
    - System health monitoring
"""

import asyncio
import logging
from typing import Dict, Any

import aiohttp

from ..user_agents import get_stealth_headers
from ..state.cache import get_cache
from ..state.session import get_session_manager

logger = logging.getLogger(__name__)


async def health_check() -> Dict[str, Any]:
    """
    Perform system health check.

    Returns status of all subsystems:
    - Browser readiness
    - Cache status
    - Session status
    - Proxy status (if configured)
    """
    try:
        cache = get_cache()
        session_mgr = get_session_manager()

        cache_stats = cache.get_stats()
        sessions = session_mgr.list_sessions()

        # Check if we can import required modules
        browser_ok = True
        try:
            import importlib.util

            browser_ok = importlib.util.find_spec("playwright") is not None
        except Exception:
            browser_ok = False

        # Get version dynamically from package
        try:
            from web_scraper_toolkit import __version__
            version = __version__
        except ImportError:
            version = "unknown"

        return {
            "status": "healthy",
            "browser": "ready" if browser_ok else "unavailable",
            "cache": {
                "enabled": cache_stats.get("enabled", False),
                "entries": cache_stats.get("memory_entries", 0),
                "hit_rate": cache_stats.get("hit_rate_percent", 0),
            },
            "sessions": {
                "count": len(sessions),
                "names": [s["session_id"] for s in sessions],
            },
            "version": version,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def validate_url(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Validate URL reachability with HEAD request.

    Args:
        url: URL to validate
        timeout: Request timeout in seconds

    Returns:
        Dict with reachability status, content type, redirects, etc.
    """
    try:
        headers = get_stealth_headers()

        async with aiohttp.ClientSession() as session:
            async with session.head(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as response:
                return {
                    "reachable": response.status < 400,
                    "status_code": response.status,
                    "content_type": response.headers.get("Content-Type", "unknown"),
                    "content_length": int(response.headers.get("Content-Length", 0)),
                    "final_url": str(response.url),
                    "redirects": len(response.history),
                }
    except asyncio.TimeoutError:
        return {
            "reachable": False,
            "error": "timeout",
            "status_code": None,
        }
    except aiohttp.ClientError as e:
        return {
            "reachable": False,
            "error": str(e),
            "status_code": None,
        }
    except Exception as e:
        logger.error(f"URL validation failed: {e}")
        return {
            "reachable": False,
            "error": str(e),
            "status_code": None,
        }


async def detect_content_type(url: str, timeout: int = 10) -> Dict[str, Any]:
    """
    Detect content type of URL without downloading full content.

    Args:
        url: URL to check
        timeout: Request timeout

    Returns:
        Dict with content type and boolean flags for common types.
    """
    result = await validate_url(url, timeout)

    if not result.get("reachable"):
        return {
            "type": "unknown",
            "is_html": False,
            "is_pdf": False,
            "is_image": False,
            "is_json": False,
            "error": result.get("error"),
        }

    content_type = result.get("content_type", "").lower()

    return {
        "type": content_type,
        "is_html": "text/html" in content_type,
        "is_pdf": "application/pdf" in content_type,
        "is_image": content_type.startswith("image/"),
        "is_json": "application/json" in content_type,
        "is_xml": "xml" in content_type,
        "is_text": content_type.startswith("text/"),
        "size_bytes": result.get("content_length", 0),
    }


async def download_file(
    url: str,
    save_path: str,
    timeout: int = 60,
    chunk_size: int = 8192,
) -> Dict[str, Any]:
    """
    Download file from URL.

    Args:
        url: URL to download
        save_path: Local path to save file
        timeout: Request timeout
        chunk_size: Download chunk size

    Returns:
        Dict with save status, path, and file info.
    """
    import os
    from pathlib import Path

    try:
        headers = get_stealth_headers()

        # Ensure directory exists
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status >= 400:
                    return {
                        "saved": False,
                        "error": f"HTTP {response.status}",
                        "status_code": response.status,
                    }

                content_type = response.headers.get("Content-Type", "unknown")
                total_size = 0

                with open(save_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(chunk_size):
                        f.write(chunk)
                        total_size += len(chunk)

                return {
                    "saved": True,
                    "path": os.path.abspath(save_path),
                    "size_bytes": total_size,
                    "content_type": content_type,
                    "url": url,
                }

    except Exception as e:
        logger.error(f"File download failed: {e}")
        return {
            "saved": False,
            "error": str(e),
        }
