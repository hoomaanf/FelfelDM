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

import keyring

from core.constants import DATA_FILE, BACKUP_FILE
from core.queue_model import Queue, Settings
from core.aria2_manager import apply_speed_limit

logger = logging.getLogger(__name__)


class DataStore:
    """Thread-safe data storage with backup recovery and speed limit application."""

    PATH = DATA_FILE
    BACKUP_PATH = BACKUP_FILE

    def __init__(self) -> None:
        self._lock = Lock()
        self.queues: List[Queue] = []
        self.settings: Settings = Settings()
        self._check_keyring()
        self.load()

    def _check_keyring(self) -> None:
        """Check keyring availability and load secret if possible, with fallback."""
        try:
            secret = keyring.get_password("felfeldm", "aria2_secret")
            if secret:
                self.settings.aria2_secret = secret
                logger.info("Loaded secret from keyring")
                return
        except Exception as e:
            logger.warning("Keyring not available: %s", e)

        secret_file = Path.home() / ".felfeldm" / "aria2_secret.txt"
        try:
            if secret_file.exists():
                with open(secret_file, "r", encoding="utf-8") as f:
                    secret = f.read().strip()
                if secret:
                    self.settings.aria2_secret = secret
                    logger.info("Loaded secret from fallback file")
                    return
        except Exception as e:
            logger.error("Failed to read fallback secret file: %s", e)

        logger.warning("No secret found; aria2 may not be secured")

    def _save_secret_to_keyring(self, secret: str) -> None:
        """Save secret to keyring, fallback to file if needed."""
        try:
            keyring.set_password("felfeldm", "aria2_secret", secret)
            logger.info("Saved secret to keyring")
            return
        except Exception as e:
            logger.warning("Failed to save to keyring: %s", e)

        secret_file = Path.home() / ".felfeldm" / "aria2_secret.txt"
        try:
            secret_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(secret)
            logger.info("Saved secret to fallback file")
        except Exception as e:
            logger.error("Failed to save secret to fallback file: %s", e)

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
                if self.BACKUP_PATH.exists():
                    try:
                        with open(self.BACKUP_PATH, 'r', encoding='utf-8') as f:
                            backup_data = json.load(f)
                        self._from_dict(backup_data)
                        logger.info("Data recovered from backup")
                        self.save()
                        return
                    except Exception as backup_e:
                        logger.error("Backup recovery failed: %s", backup_e)
                logger.warning("Starting with default data due to corruption")
                self._reset_defaults()

    def _reset_defaults(self) -> None:
        self.queues = []
        self.settings = Settings()

    def _from_dict(self, data: Dict[str, Any]) -> None:
        self.queues = [Queue.from_dict(q) for q in data.get("queues", [])]
        settings_data = data.get("settings", {})
        self.settings = Settings(
            download_dir=settings_data.get("download_dir", ""),
            speed_limit=settings_data.get("speed_limit", 0),
            max_concurrent=settings_data.get("max_concurrent", 5),
            aria2_secret=settings_data.get("aria2_secret", "")
        )
        if self.settings.aria2_secret:
            self._save_secret_to_keyring(self.settings.aria2_secret)

    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "queues": [q.to_dict() for q in self.queues],
                "settings": self.settings.to_dict()
            }

    def save(self) -> None:
        with self._lock:
            try:
                if self.PATH.exists():
                    shutil.copy2(self.PATH, self.BACKUP_PATH)
                data = self.to_dict()
                with open(self.PATH, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info("Data saved")
            except Exception as e:
                logger.error("Failed to save data: %s", e)

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

    def apply_speed_limit(self) -> bool:
        """
        Apply the current speed_limit setting to aria2 via RPC.
        Returns True on success, False on failure.
        """
        if not self.settings.aria2_secret:
            logger.error("No aria2 secret set; cannot apply speed limit")
            return False
        return apply_speed_limit(
            secret=self.settings.aria2_secret,
            speed_limit=self.settings.speed_limit
        )
