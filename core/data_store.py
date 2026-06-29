# core/data_store.py
"""
Persistent data store with secure secret handling and thread-safety.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any

import keyring

from core.constants import (
    CONFIG_DIR,
    KEYRING_SERVICE,
    KEYRING_KEY,
    DEFAULT_DOWNLOAD_PATH,
)
from core.queue_model import Queue

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Type-safe settings container."""
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
    default_download_path: str = str(DEFAULT_DOWNLOAD_PATH)

    def to_dict(self) -> Dict[str, Any]:
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
            default_download_path=data.get("default_download_path", str(DEFAULT_DOWNLOAD_PATH)),
        )


class DataStore:
    """Persistent data store with secure secret handling."""

    PATH: Path = CONFIG_DIR / "data.json"

    def __init__(self) -> None:
        self._lock = Lock()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        self.queues: List[Queue] = []
        self.settings: Settings = Settings()

        self.load()

        if not self._has_default_queue():
            self.queues.insert(0, Queue("Default", paused=True))
            self.save()

    def _has_default_queue(self) -> bool:
        return any(q.name == "Default" for q in self.queues)

    def _sync_secret_from_keyring(self) -> None:
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
        with self._lock:
            if not self.PATH.exists():
                return

            try:
                with self.PATH.open("r", encoding="utf-8") as f:
                    data = json.load(f)

                self.queues = []
                for q_data in data.get("queues", []):
                    self.queues.append(Queue.from_dict(q_data))

                if "settings" in data:
                    self.settings = Settings.from_dict(data["settings"])

                self._sync_secret_from_keyring()
                logger.info("Loaded %d queues", len(self.queues))

            except Exception as e:
                logger.error("Failed to load data: %s", e)

    def save(self) -> None:
        with self._lock:
            try:
                data = {
                    "queues": [q.to_dict() for q in self.queues],
                    "settings": self.settings.to_dict(),
                }

                if self.settings.aria2_secret:
                    try:
                        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings.aria2_secret)
                    except Exception as e:
                        logger.warning("Failed to save secret to keyring: %s", e)

                with self.PATH.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.debug("Data saved")

            except Exception as e:
                logger.error("Failed to save data: %s", e)

    def get_secret(self) -> str:
        self._sync_secret_from_keyring()
        return self.settings.aria2_secret

    def set_secret(self, secret: str) -> None:
        self.settings.aria2_secret = secret
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
        except Exception as e:
            logger.warning("Failed to save secret to keyring: %s", e)
        self.save()

    def get_default_download_path(self) -> str:
        return self.settings.default_download_path

    def set_default_download_path(self, path: str) -> None:
        self.settings.default_download_path = path
        self.save()

    def get_queue(self, name: str) -> Optional[Queue]:
        for q in self.queues:
            if q.name == name:
                return q
        return None

    def get_queue_index(self, name: str) -> Optional[int]:
        for i, q in enumerate(self.quques):
            if q.name == name:
                return i
        return None
