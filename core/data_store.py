# =============================================================================
# core/data_store.py
# =============================================================================
import json
import logging
import os
import shutil
from pathlib import Path
from threading import Lock
from typing import List, Optional, Dict, Any

from core.constants import DATA_FILE, BACKUP_FILE
from core.queue_model import Queue, Settings

logger = logging.getLogger(__name__)


class DataStore:
    """Thread-safe data storage with backup recovery."""

    PATH = DATA_FILE
    BACKUP_PATH = BACKUP_FILE

    def __init__(self):
        self._lock = Lock()
        self.queues: List[Queue] = []
        self.settings: Settings = Settings()
        self.load()

    def load(self) -> None:
        """Load data from file with error handling and backup recovery."""
        with self._lock:
            if not self.PATH.exists():
                logger.info("Data file not found, starting with defaults")
                self._reset_defaults()
                return

            try:
                with open(self.PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._from_dict(data)
                logger.info("Data loaded successfully")
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.error("Failed to load data: %s", e)
                # Try backup recovery
                if self.BACKUP_PATH.exists():
                    try:
                        with open(self.BACKUP_PATH, 'r', encoding='utf-8') as f:
                            backup_data = json.load(f)
                        self._from_dict(backup_data)
                        logger.info("Data recovered from backup")
                        # Save recovered data to main file
                        self.save()
                        return
                    except Exception as backup_e:
                        logger.error("Backup recovery failed: %s", backup_e)
                # If all fails, start with defaults but keep existing file for inspection
                logger.warning("Starting with default data due to corruption")
                self._reset_defaults()

    def _reset_defaults(self) -> None:
        """Reset to default empty state."""
        self.queues = []
        self.settings = Settings()

    def _from_dict(self, data: Dict[str, Any]) -> None:
        """Populate from dict."""
        # Expecting keys: "queues", "settings"
        self.queues = [Queue.from_dict(q) for q in data.get("queues", [])]
        settings_data = data.get("settings", {})
        self.settings = Settings(
            download_dir=settings_data.get("download_dir", ""),
            speed_limit=settings_data.get("speed_limit", 0),
            max_concurrent=settings_data.get("max_concurrent", 5),
            aria2_secret=settings_data.get("aria2_secret", "")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        with self._lock:
            return {
                "queues": [q.to_dict() for q in self.queues],
                "settings": self.settings.to_dict()
            }

    def save(self) -> None:
        """Save data to file, creating backup first."""
        with self._lock:
            try:
                # Backup existing file
                if self.PATH.exists():
                    shutil.copy2(self.PATH, self.BACKUP_PATH)

                data = self.to_dict()
                with open(self.PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info("Data saved")
            except Exception as e:
                logger.error("Failed to save data: %s", e)

    # Additional methods for manipulating queues, etc.
    def add_queue(self, queue: Queue) -> None:
        with self._lock:
            self.queues.append(queue)
            self.save()

    def remove_queue(self, queue_id: str) -> None:
        with self._lock:
            self.queues = [q for q in self.queues if q.id != queue_id]
            self.save()

    def get_queue(self, queue_id: str) -> Optional[Queue]:
        with self._lock:
            for q in self.queues:
                if q.id == queue_id:
                    return q
            return None

    def update_queue(self, queue: Queue) -> None:
        with self._lock:
            for i, q in enumerate(self.queues):
                if q.id == queue.id:
                    self.queues[i] = queue
                    break
            self.save()
