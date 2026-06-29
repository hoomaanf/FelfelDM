# core/data_store.py
"""
Persistent data store with secure secret handling and thread-safety.
Synchronizes aria2_secret between settings (source of truth) and keyring.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from threading import Lock
from typing import Optional, List, Dict, Any

import keyring
from appdirs import user_config_dir

from core.queue_model import Queue

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"


@dataclass
class Settings:
    """
    Type-safe settings container for the application.
    """
    aria2_host: str = "http://localhost"
    aria2_port: int = 6800
    aria2_secret: str = ""
    connections: int = 8
    max_tries: int = 0
    max_concurrent: int = 5
    shutdown_after_finish: bool = False
    speed_limit: int = 0
    auto_clear_completed: bool = False
    theme: str = "system"
    default_download_path: str = field(default_factory=lambda: os.path.expanduser("~/Downloads"))

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to a dictionary for JSON serialization."""
        return {
            "aria2_host": self.aria2_host,
            "aria2_port": self.aria2_port,
            "aria2_secret": self.aria2_secret,
            "connections": self.connections,
            "max_tries": self.max_tries,
            "max_concurrent": self.max_concurrent,
            "shutdown_after_finish": self.shutdown_after_finish,
            "speed_limit": self.speed_limit,
            "auto_clear_completed": self.auto_clear_completed,
            "theme": self.theme,
            "default_download_path": self.default_download_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """Create Settings from a dictionary."""
        return cls(
            aria2_host=data.get("aria2_host", "http://localhost"),
            aria2_port=data.get("aria2_port", 6800),
            aria2_secret=data.get("aria2_secret", ""),
            connections=data.get("connections", 8),
            max_tries=data.get("max_tries", 0),
            max_concurrent=data.get("max_concurrent", 5),
            shutdown_after_finish=data.get("shutdown_after_finish", False),
            speed_limit=data.get("speed_limit", 0),
            auto_clear_completed=data.get("auto_clear_completed", False),
            theme=data.get("theme", "system"),
            default_download_path=data.get("default_download_path", os.path.expanduser("~/Downloads")),
        )


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
        self.settings: Settings = Settings()

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
                if self.settings.aria2_secret != secret:
                    self.settings.aria2_secret = secret
                    logger.debug("Secret synced from keyring to settings")
            else:
                if self.settings.aria2_secret:
                    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings.aria2_secret)
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
                    self.settings = Settings.from_dict(data["settings"])

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
                    "settings": self.settings.to_dict(),
                }

                # Save secret to keyring
                if self.settings.aria2_secret:
                    try:
                        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings.aria2_secret)
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
        return self.settings.aria2_secret

    def set_secret(self, secret: str) -> None:
        """Set the aria2 secret and sync to keyring."""
        self.settings.aria2_secret = secret
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
        except Exception as e:
            logger.warning("Failed to save secret to keyring: %s", e)
        self.save()

    def get_default_download_path(self) -> str:
        """Get the default download path."""
        return self.settings.default_download_path

    def set_default_download_path(self, path: str) -> None:
        """Set the default download path."""
        self.settings.default_download_path = path
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
