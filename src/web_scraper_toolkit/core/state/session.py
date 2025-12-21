# ./src/web_scraper_toolkit/core/state/session.py
"""
Session Management
==================

Browser session persistence and management.
Supports saving/loading session state across runs.

Usage:
    session_mgr = SessionManager(config)
    await session_mgr.save_state(context)
    await session_mgr.load_state(context)

Key Features:
    - Cookie persistence
    - Local storage preservation
    - Session directory management
    - Clear session support
"""

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SessionConfig:
    """Configuration for session management."""

    persist: bool = True
    directory: str = "./sessions"
    reuse_browser: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionConfig":
        return cls(
            persist=data.get("persist", True),
            directory=data.get("directory", "./sessions"),
            reuse_browser=data.get("reuse_browser", True),
        )


class SessionManager:
    """
    Manages browser session state persistence.

    Enables session reuse across headless/headed mode switches
    and preserves login state for authenticated scraping.
    """

    def __init__(self, config: Optional[SessionConfig] = None):
        self.config = config or SessionConfig()

        # Ensure session directory exists
        if self.config.persist:
            Path(self.config.directory).mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str = "default") -> Path:
        """Get path for session state files."""
        return Path(self.config.directory) / session_id

    def _get_cookies_path(self, session_id: str = "default") -> Path:
        """Get path for cookies file."""
        return self._get_session_path(session_id) / "cookies.json"

    def _get_storage_path(self, session_id: str = "default") -> Path:
        """Get path for Playwright storage state."""
        return self._get_session_path(session_id) / "storage_state.json"

    async def save_state(
        self,
        context,  # Playwright BrowserContext
        session_id: str = "default",
    ) -> bool:
        """
        Save browser context state.

        Args:
            context: Playwright BrowserContext
            session_id: Session identifier

        Returns:
            True if saved successfully
        """
        if not self.config.persist:
            return False

        try:
            session_path = self._get_session_path(session_id)
            session_path.mkdir(parents=True, exist_ok=True)

            # Save Playwright storage state (cookies + localStorage)
            storage_path = self._get_storage_path(session_id)
            await context.storage_state(path=str(storage_path))

            # Save metadata
            metadata_path = session_path / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(
                    {
                        "saved_at": datetime.now().isoformat(),
                        "session_id": session_id,
                    },
                    f,
                )

            logger.info(f"Session saved: {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            return False

    def get_storage_state_path(self, session_id: str = "default") -> Optional[str]:
        """
        Get path to storage state file if it exists.

        Used when creating new browser contexts.
        """
        storage_path = self._get_storage_path(session_id)
        if storage_path.exists():
            return str(storage_path)
        return None

    def has_session(self, session_id: str = "default") -> bool:
        """Check if a saved session exists."""
        return self._get_storage_path(session_id).exists()

    def clear_session(self, session_id: str = "default") -> dict:
        """
        Clear a specific session.

        Returns stats about cleared data.
        """
        session_path = self._get_session_path(session_id)

        if not session_path.exists():
            return {"cleared": False, "reason": "Session not found"}

        try:
            shutil.rmtree(session_path)
            logger.info(f"Session cleared: {session_id}")
            return {"cleared": True, "session_id": session_id}
        except Exception as e:
            logger.error(f"Failed to clear session: {e}")
            return {"cleared": False, "error": str(e)}

    def clear_all_sessions(self) -> dict:
        """Clear all saved sessions."""
        session_dir = Path(self.config.directory)

        if not session_dir.exists():
            return {"cleared_count": 0}

        cleared = 0
        for item in session_dir.iterdir():
            if item.is_dir():
                try:
                    shutil.rmtree(item)
                    cleared += 1
                except Exception as e:
                    logger.warning(f"Failed to clear session {item.name}: {e}")

        logger.info(f"Cleared {cleared} sessions")
        return {"cleared_count": cleared}

    def list_sessions(self) -> list:
        """List all saved sessions."""
        session_dir = Path(self.config.directory)

        if not session_dir.exists():
            return []

        sessions = []
        for item in session_dir.iterdir():
            if item.is_dir():
                metadata_path = item / "metadata.json"
                metadata = {}
                if metadata_path.exists():
                    try:
                        with open(metadata_path) as f:
                            metadata = json.load(f)
                    except Exception:
                        pass

                sessions.append(
                    {
                        "session_id": item.name,
                        "saved_at": metadata.get("saved_at"),
                        "has_cookies": (item / "cookies.json").exists(),
                        "has_storage": (item / "storage_state.json").exists(),
                    }
                )

        return sessions


# Global session manager instance
_global_session_manager: Optional[SessionManager] = None


def get_session_manager(config: Optional[SessionConfig] = None) -> SessionManager:
    """Get or create global session manager."""
    global _global_session_manager
    if _global_session_manager is None:
        _global_session_manager = SessionManager(config)
    return _global_session_manager
