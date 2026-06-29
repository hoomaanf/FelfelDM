# core/history.py
"""
Download history management with persistence.
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from core.constants import HISTORY_FILE

logger = logging.getLogger(__name__)


@dataclass
class DownloadHistory:
    """Represent a completed download entry."""

    gid: str
    name: str
    url: str
    size: int
    status: str
    start_time: str
    end_time: str
    save_path: str
    category: str = "Other"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DownloadHistory":
        return cls(**data)


class HistoryManager:
    """
    Manages download history with persistence to JSON file.
    """

    def __init__(self) -> None:
        self.history: List[DownloadHistory] = []
        self._file_path = HISTORY_FILE
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self) -> None:
        """Load history from file."""
        if not self._file_path.exists():
            return

        try:
            with self._file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                entries = data.get("history", [])
                self.history = [DownloadHistory.from_dict(entry) for entry in entries]
            logger.info("Loaded %d history entries", len(self.history))
        except Exception as e:
            logger.error("Failed to load history: %s", e)
            self.history = []

    def save(self) -> None:
        """Save history to file."""
        try:
            data = {
                "history": [entry.to_dict() for entry in self.history],
                "timestamp": datetime.now().isoformat(),
            }
            with self._file_path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("History saved")
        except Exception as e:
            logger.error("Failed to save history: %s", e)

    def add(self, entry: DownloadHistory) -> None:
        """Add a new entry to history."""
        self.history.append(entry)
        # Limit history to 1000 entries to prevent bloat
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        self.save()

    def get_all(self) -> List[DownloadHistory]:
        """Get all history entries (sorted by end time descending)."""
        return sorted(
            self.history,
            key=lambda x: x.end_time,
            reverse=True
        )

    def search(self, query: str) -> List[DownloadHistory]:
        """Search history by name or URL."""
        if not query:
            return self.get_all()
        query_lower = query.lower()
        results = []
        for entry in self.history:
            if (query_lower in entry.name.lower() or
                query_lower in entry.url.lower() or
                query_lower in entry.gid.lower()):
                results.append(entry)
        return sorted(results, key=lambda x: x.end_time, reverse=True)

    def clear(self) -> None:
        """Clear all history."""
        self.history = []
        self.save()

    def get_by_gid(self, gid: str) -> Optional[DownloadHistory]:
        """Find a history entry by GID."""
        for entry in self.history:
            if entry.gid == gid:
                return entry
        return None
