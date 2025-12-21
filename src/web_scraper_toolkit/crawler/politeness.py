# ./src/web_scraper_toolkit/crawler/politeness.py
"""
Politeness Manager
==================

Handles robots.txt parsing and crawl delays.
Can be disabled via configuration.
"""

import asyncio
import logging
import urllib.robotparser
from urllib.parse import urlparse
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PolitenessManager:
    def __init__(self, user_agent: str = "*", respect_robots: bool = True):
        self.user_agent = user_agent
        self.respect_robots = respect_robots
        # Cache parsers per domain
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        # Global locks for domain concurrency
        self._domain_locks: Dict[str, asyncio.Lock] = {}

    def _get_domain(self, url: str) -> str:
        return urlparse(url).netloc

    def get_domain_lock(self, url: str) -> asyncio.Lock:
        """Returns an async lock specific to the domain for throttle control."""
        domain = self._get_domain(url)
        if domain not in self._domain_locks:
            self._domain_locks[domain] = asyncio.Lock()
        return self._domain_locks[domain]

    async def can_fetch(self, url: str) -> bool:
        """Checks if robots.txt allows fetching this URL."""
        if not self.respect_robots:
            return True

        domain = self._get_domain(url)
        parser = await self._get_parser(domain)
        if not parser:
            return True  # If robots.txt fails/missing, assume default allow

        return parser.can_fetch(self.user_agent, url)

    async def _get_parser(
        self, domain: str
    ) -> Optional[urllib.robotparser.RobotFileParser]:
        if domain in self._parsers:
            return self._parsers[domain]

        robots_url = f"https://{domain}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)

        try:
            # Fetch synchronously inside thread (robotparser is blocking)
            # Or use aiohttp to fetch string, then parse.
            # parser.read() is blocking.
            # Better: Fetch content manually, then parse(lines)
            await asyncio.to_thread(parser.read)
            self._parsers[domain] = parser
            return parser
        except Exception as e:
            logger.warning(f"Failed to fetch/parse robots.txt for {domain}: {e}")
            return None
