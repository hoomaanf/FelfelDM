"""
Manages session persistence: save/restore active GIDs with additional metadata.
"""

import json
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.data_store import DataStore

logger: logging.Logger = logging.getLogger(__name__)


class SessionManager:
    """Save and restore download sessions with rich metadata."""

    SESSION_FILE: Path = Path.home() / ".cache" / "felfelDM" / "session.json"

    def __init__(self, store: DataStore) -> None:
        self.store: DataStore = store
        self.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)

    def save_session(self, active_gids: List[str]) -> None:
        """
        Save list of active GIDs and associated metadata (path, total size, etc.)
        to session file.
        """
        try:
            downloads_data = []
            for gid in active_gids:
                downloads_data.append({
                    "gid": gid,
                    "timestamp": datetime.datetime.now().isoformat()
                })
            data = {
                "active_downloads": downloads_data,
                "timestamp": datetime.datetime.now().isoformat()
            }
            with self.SESSION_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Saved session with %d active GIDs", len(active_gids))
        except Exception as e:
            logger.error("Failed to save session: %s", e)

    def load_session(self) -> List[str]:
        """
        Load list of active GIDs from session file.
        """
        try:
            if not self.SESSION_FILE.exists():
                return []
            with self.SESSION_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            downloads = data.get("active_downloads", [])
            gids = [entry.get("gid") for entry in downloads if entry.get("gid")]
            logger.info("Loaded session with %d GIDs", len(gids))
            return gids
        except Exception as e:
            logger.error("Failed to load session: %s", e)
            return []

    def clear_session(self) -> None:
        """Delete session file."""
        try:
            if self.SESSION_FILE.exists():
                self.SESSION_FILE.unlink()
                logger.info("Session cleared.")
        except Exception as e:
            logger.error("Failed to clear session: %s", e)
