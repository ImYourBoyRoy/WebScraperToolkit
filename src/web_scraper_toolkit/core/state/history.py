# ./src/web_scraper_toolkit/core/state/history.py
"""
Scrape History
==============

Track and replay past scraping operations.
Useful for auditing, debugging, and replaying operations.

Usage:
    history = get_history_manager()
    history.log_scrape(url, status="success")
    recent = history.get_recent(limit=10)

Key Features:
    - Persistent history tracking
    - Configurable retention
    - Search and filter
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    """Single history entry."""

    url: str
    timestamp: str
    status: str  # success, error, cached
    duration_ms: Optional[int] = None
    cached: bool = False
    content_type: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HistoryConfig:
    """Configuration for history tracking."""

    enabled: bool = True
    directory: str = "./history"
    max_entries: int = 1000

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryConfig":
        return cls(
            enabled=data.get("enabled", True),
            directory=data.get("directory", "./history"),
            max_entries=data.get("max_entries", 1000),
        )


class HistoryManager:
    """
    Manages scrape history tracking and retrieval.
    """

    def __init__(self, config: Optional[HistoryConfig] = None):
        self.config = config or HistoryConfig()
        self._entries: List[HistoryEntry] = []
        self._history_file = Path(self.config.directory) / "scrape_history.json"

        if self.config.enabled:
            Path(self.config.directory).mkdir(parents=True, exist_ok=True)
            self._load()

    def _load(self) -> None:
        """Load history from disk."""
        if self._history_file.exists():
            try:
                with open(self._history_file, "r") as f:
                    data = json.load(f)
                    self._entries = [HistoryEntry(**entry) for entry in data]
            except Exception as e:
                logger.warning(f"Failed to load history: {e}")
                self._entries = []

    def _save(self) -> None:
        """Save history to disk."""
        if not self.config.enabled:
            return
        try:
            with open(self._history_file, "w") as f:
                json.dump([e.to_dict() for e in self._entries], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save history: {e}")

    def log_scrape(
        self,
        url: str,
        status: str = "success",
        duration_ms: Optional[int] = None,
        cached: bool = False,
        content_type: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log a scrape operation."""
        if not self.config.enabled:
            return

        entry = HistoryEntry(
            url=url,
            timestamp=datetime.now().isoformat(),
            status=status,
            duration_ms=duration_ms,
            cached=cached,
            content_type=content_type,
            error=error,
        )

        self._entries.append(entry)

        # Trim if exceeds max
        if len(self._entries) > self.config.max_entries:
            self._entries = self._entries[-self.config.max_entries :]

        self._save()

    def get_recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recent history entries."""
        return [e.to_dict() for e in self._entries[-limit:]][::-1]

    def search(self, url_pattern: str) -> List[Dict[str, Any]]:
        """Search history by URL pattern."""
        matches = [
            e.to_dict() for e in self._entries if url_pattern.lower() in e.url.lower()
        ]
        return matches[::-1]  # Most recent first

    def get_stats(self) -> Dict[str, Any]:
        """Get history statistics."""
        if not self._entries:
            return {"total": 0}

        success_count = sum(1 for e in self._entries if e.status == "success")
        error_count = sum(1 for e in self._entries if e.status == "error")
        cached_count = sum(1 for e in self._entries if e.cached)

        return {
            "total": len(self._entries),
            "success": success_count,
            "errors": error_count,
            "cached": cached_count,
            "success_rate": round(success_count / len(self._entries) * 100, 1),
        }

    def clear(self) -> Dict[str, Any]:
        """Clear all history."""
        count = len(self._entries)
        self._entries = []
        self._save()
        return {"cleared": count}


# Global history manager
_global_history: Optional[HistoryManager] = None


def get_history_manager(config: Optional[HistoryConfig] = None) -> HistoryManager:
    """Get or create global history manager."""
    global _global_history
    if _global_history is None:
        _global_history = HistoryManager(config)
    return _global_history
