# ./src/web_scraper_toolkit/crawler/frontier.py
"""
URL Frontier
============

Manages the queue of URLs to visit.
Features:
-   Priority Management
-   De-duplication (Seen URLs)
-   Depth Tracking
"""

import asyncio
from typing import Set
from dataclasses import dataclass, field
import heapq


@dataclass(order=True)
class FrontierItem:
    priority: int  # Lower is better
    url: str = field(compare=False)
    depth: int = field(compare=False)
    # Metadata for processing context
    meta: dict = field(default_factory=dict, compare=False)


class Frontier:
    def __init__(self):
        self._queue = []  # Heap Queue
        self._seen: Set[str] = set()
        self._lock = asyncio.Lock()
        self._count = 0  # Push counter specifically for stable sorting if needed (heapq is not stable)

    async def add_url(
        self, url: str, depth: int = 0, priority: int = 10, meta: dict = None
    ):
        """Adds a URL to the frontier if not already seen."""
        async with self._lock:
            if url in self._seen:
                return

            self._seen.add(url)
            # Use heapq for priority queue
            heapq.heappush(self._queue, FrontierItem(priority, url, depth, meta or {}))

    async def get_next(self) -> FrontierItem:
        """Pops the highest priority (lowest number) item."""
        async with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)

    def is_empty(self) -> bool:
        return len(self._queue) == 0

    def __len__(self):
        return len(self._queue)
