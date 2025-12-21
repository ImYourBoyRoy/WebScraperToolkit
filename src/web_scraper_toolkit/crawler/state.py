# ./src/web_scraper_toolkit/crawler/state.py
"""
Crawler State Manager
=====================

Handles persistence of seen URLs and progress.
Uses JSON for simplicity (upgradeable to SQLite).
"""

import json
import os
import logging
from typing import Set, Dict, Any

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, filepath: str = "crawl_state.json"):
        self.filepath = filepath
        self.seen: Set[str] = set()
        self.meta: Dict[str, Any] = {}

    def load(self):
        """Loads state from file if exists."""
        if not os.path.exists(self.filepath):
            return

        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
                self.seen = set(data.get("seen", []))
                self.meta = data.get("meta", {})
            logger.info(f"Loaded crawler state: {len(self.seen)} items seen.")
        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    def save(self):
        """Saves current state to file."""
        try:
            data = {"seen": list(self.seen), "meta": self.meta}
            with open(self.filepath, "w") as f:
                json.dump(data, f)
            # logger.debug("State saved.")
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def add_seen(self, url: str):
        self.seen.add(url)

    def is_seen(self, url: str) -> bool:
        return url in self.seen
