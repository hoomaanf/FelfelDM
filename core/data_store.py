# core/data_store.py
"""
Persistent data store with secure secret handling and thread-safety.
Synchronizes aria2_secret between settings and keyring.
"""

import json
import logging
import os
from datetime import datetime, time as dtime
from threading import Lock
from typing import Optional, List, Dict, Any

import keyring
from appdirs import user_config_dir

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"


class Queue:
    """Download queue model - single source of truth."""

    def __init__(
        self,
        name: str,
        max_concurrent: int = 3,
        save_path: str = "",
        schedule_enabled: bool = False,
        schedule_start=None,
        schedule_end=None,
        days=None,
        paused: bool = True,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or os.path.expanduser("~/Downloads")
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads: List[str] = []  # List of GIDs
        self.paused = paused

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "save_path": self.save_path,
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": self.schedule_start.strftime("%H:%M"),
            "schedule_end": self.schedule_end.strftime("%H:%M"),
            "days": self.days,
            "downloads": self.downloads,
            "paused": self.paused,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Queue":
        name = d.get("name", "Default")
        q = cls(name)
        q.max_concurrent = d.get("max_concurrent", 3)
        q.save_path = d.get("save_path", os.path.expanduser("~/Downloads"))
        q.schedule_enabled = d.get("schedule_enabled", False)

        st = d.get("schedule_start", "00:00").split(":")
        en = d.get("schedule_end", "23:59").split(":")
        q.schedule_start = dtime(int(st[0]), int(st[1]))
        q.schedule_end = dtime(int(en[0]), int(en[1]))

        q.days = d.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(d.get("downloads", []))
        q.paused = d.get("paused", True)
        return q

    def is_scheduled_now(self) -> bool:
        """Check if the queue is allowed to run based on schedule."""
        if not self.schedule_enabled:
            return True
        now = datetime.now()
        if now.weekday() not in self.days:
            return False
        t = now.time().replace(second=0, microsecond=0)
        start = self.schedule_start
        end = self.schedule_end
        if start <= end:
            return start <= t <= end
        return t >= start or t <= end


class DataStore:
    """
    Persistent data store with secure secret handling and thread-safety.
    Synchronizes aria2_secret between settings (source of truth) and keyring.
    """

    PATH = os.path.join(user_config_dir("felfelDM"), "data.json")

    def __init__(self) -> None:
        self._lock = Lock()
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)

        self.queues: List[Queue] = []
        self.settings: Dict[str, Any] = {
            "aria2_host": "http://localhost",
            "aria2_port": 6800,
            "aria2_secret": "",
            "connections": 8,
            "max_tries": 0,
            "max_concurrent": 5,
            "shutdown_after_finish": False,
            "speed_limit": 0,
            "auto_clear_completed": False,
        }

        self.load()

        # Ensure Default queue exists
        if not self._has_default_queue():
            self.queues.insert(0, Queue("Default", paused=True))
            self.save()

    def _has_default_queue(self) -> bool:
        return any(q.name == "Default" for q in self.queues)

    def _sync_secret_from_keyring(self) -> None:
        """Load secret from keyring and update settings if present."""
        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
            if secret:
                if self.settings.get("aria2_secret") != secret:
                    self.settings["aria2_secret"] = secret
                    logger.debug("Secret synced from keyring to settings")
            else:
                # If keyring has no secret but settings does, save to keyring
                if self.settings.get("aria2_secret"):
                    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings["aria2_secret"])
                    logger.debug("Secret synced from settings to keyring")
        except Exception as e:
            logger.warning("Failed to sync secret from keyring: %s", e)

    def load(self) -> None:
        """Load data from file with thread-safety."""
        with self._lock:
            if not os.path.exists(self.PATH):
                return

            try:
                with open(self.PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Load queues
                self.queues = []
                for q_data in data.get("queues", []):
                    self.queues.append(Queue.from_dict(q_data))

                # Load settings
                if "settings" in data:
                    self.settings.update(data["settings"])

                # Sync secret from keyring
                self._sync_secret_from_keyring()

                logger.info("Loaded %d queues", len(self.queues))

            except Exception as e:
                logger.error("Failed to load data: %s", e)

    def save(self) -> None:
        """Save data to file with thread-safety."""
        with self._lock:
            try:
                data = {
                    "queues": [q.to_dict() for q in self.queues],
                    "settings": self.settings,
                }

                # Save secret to keyring
                secret = self.settings.get("aria2_secret")
                if secret:
                    try:
                        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
                    except Exception as e:
                        logger.warning("Failed to save secret to keyring: %s", e)

                with open(self.PATH, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.debug("Data saved")

            except Exception as e:
                logger.error("Failed to save data: %s", e)

    def get_secret(self) -> str:
        """Get the aria2 secret, ensuring it's synced with keyring."""
        self._sync_secret_from_keyring()
        return self.settings.get("aria2_secret", "")

    def set_secret(self, secret: str) -> None:
        """Set the aria2 secret and sync to keyring."""
        self.settings["aria2_secret"] = secret
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
        except Exception as e:
            logger.warning("Failed to save secret to keyring: %s", e)
        self.save()

    def get_queue(self, name: str) -> Optional[Queue]:
        """Get a queue by name."""
        for q in self.queues:
            if q.name == name:
                return q
        return None

    def get_queue_index(self, name: str) -> Optional[int]:
        """Get the index of a queue by name."""
        for i, q in enumerate(self.queues):
            if q.name == name:
                return i
        return None
