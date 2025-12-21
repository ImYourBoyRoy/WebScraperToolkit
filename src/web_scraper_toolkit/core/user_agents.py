# ./src/web_scraper_toolkit/core/user_agents.py
"""
User-Agent Management
=====================

Centralized, randomized user-agent pool for stealth HTTP requests.
Used by aiohttp, requests, and other non-Playwright HTTP clients.

For Playwright browser contexts, we deliberately use the NATIVE browser UA
(not setting a custom one) to match TLS fingerprints. This module is for
plain HTTP requests only.

Best Practices:
    - Rotate user-agents to avoid fingerprinting
    - Use realistic, current browser versions
    - Match common browser market share distribution
"""

import random
from typing import Dict, Optional

# Realistic, modern user-agents (Updated December 2024)
# Distribution weighted toward Chrome (dominant market share)
USER_AGENT_POOL = [
    # Chrome on Windows (most common)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
    # Chrome on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    # Safari on Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]


def get_random_user_agent() -> str:
    """Returns a random realistic user-agent string."""
    return random.choice(USER_AGENT_POOL)


def get_stealth_headers(
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """
    Returns a complete set of stealth headers for HTTP requests.

    Includes User-Agent and other headers that help avoid bot detection.
    """
    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    if extra_headers:
        headers.update(extra_headers)

    return headers


# Simple header (just User-Agent) for lightweight requests like robots.txt
def get_simple_headers() -> Dict[str, str]:
    """Returns minimal headers with just User-Agent for simple requests."""
    return {"User-Agent": get_random_user_agent()}
