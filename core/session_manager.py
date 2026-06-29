# core/session_manager.py
"""
Manages session persistence: save/restore active GIDs with rich metadata
including file path, total size, and status.
"""

import json
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import QTimer, QObject

from core.data_store import DataStore

logger: logging.Logger = logging.getLogger(__name__)


class SessionManager(QObject):
    """
    Save and restore download sessions with rich metadata.
    Auto-saves periodically every 30 seconds.
    """

    SESSION_FILE: Path = Path.home() / ".cache" / "felfelDM" / "session.json"

    def __init__(self, store: DataStore) -> None:
        super().__init__()
        self.store: DataStore = store
        self.SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        self._active_downloads: List[Dict[str, Any]] = []

        # Setup periodic save timer
        self._save_timer = QTimer()
        self._save_timer.timeout.connect(self._periodic_save)
        self._save_timer.start(30000)  # 30 seconds

    def save_session(self, active_downloads: List[Dict[str, Any]]) -> None:
        """
        Save list of active downloads with rich metadata to session file.

        Args:
            active_downloads: List of dicts containing at least 'gid', and optionally
                              'path', 'total_size', 'status', 'name', 'completed_length'.
        """
        self._active_downloads = active_downloads
        self._do_save()

    def _do_save(self) -> None:
        """Internal method to save the current session."""
        try:
            downloads_data = []
            for dl in self._active_downloads:
                entry = {
                    "gid": dl.get("gid"),
                    "timestamp": datetime.datetime.now().isoformat(),
                }
                for field in ["path", "total_size", "status", "name", "completed_length", "save_path"]:
                    if field in dl and dl[field] is not None:
                        entry[field] = dl[field]

                downloads_data.append(entry)

            data = {
                "active_downloads": downloads_data,
                "timestamp": datetime.datetime.now().isoformat(),
            }

            with self.SESSION_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.debug("Saved session with %d active downloads", len(self._active_downloads))

        except Exception as e:
            logger.error("Failed to save session: %s", e)

    def _periodic_save(self) -> None:
        """Periodic save triggered by timer."""
        if self._active_downloads:
            self._do_save()

    def load_session(self) -> List[Dict[str, Any]]:
        """
        Load list of active downloads with metadata from session file.

        Returns:
            List of dicts containing download metadata.
        """
        try:
            if not self.SESSION_FILE.exists():
                return []

            with self.SESSION_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)

            downloads = data.get("active_downloads", [])
            logger.info("Loaded session with %d downloads", len(downloads))
            self._active_downloads = downloads
            return downloads

        except Exception as e:
            logger.error("Failed to load session: %s", e)
            return []

    def load_gids(self) -> List[str]:
        """Load just the list of GIDs from the session file."""
        downloads = self.load_session()
        return [dl.get("gid") for dl in downloads if dl.get("gid")]

    def clear_session(self) -> None:
        """Delete session file."""
        try:
            if self.SESSION_FILE.exists():
                self.SESSION_FILE.unlink()
                self._active_downloads = []
                logger.info("Session cleared.")
        except Exception as e:
            logger.error("Failed to clear session: %s", e)

    def stop(self) -> None:
        """Stop the periodic save timer and save final state."""
        self._save_timer.stop()
        if self._active_downloads:
            self._do_save()
