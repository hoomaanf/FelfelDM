# core/data_store.py
"""
Persistent data store with secure secret handling, thread-safety,
and graceful fallback when keyring is unavailable.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any

import keyring
from keyring.errors import KeyringError, NoKeyringError

from core.constants import (
    CONFIG_DIR,
    KEYRING_SERVICE,
    KEYRING_KEY,
    DEFAULT_DOWNLOAD_PATH,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_CONNECTIONS,
)
from core.queue_model import Queue

logger = logging.getLogger(__name__)


@dataclass
class Settings:
    """Type-safe settings container with defaults."""
    aria2_host: str = "http://localhost"
    aria2_port: int = 6800
    aria2_secret: str = ""
    connections: int = DEFAULT_MAX_CONNECTIONS
    max_tries: int = 0
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    shutdown_after_finish: bool = False
    speed_limit: int = 0
    auto_clear_completed: bool = False
    theme: str = "system"
    default_download_path: str = str(DEFAULT_DOWNLOAD_PATH)
    async_mode: bool = False

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
            "async_mode": self.async_mode,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        return cls(
            aria2_host=data.get("aria2_host", "http://localhost"),
            aria2_port=data.get("aria2_port", 6800),
            aria2_secret=data.get("aria2_secret", ""),
            connections=data.get("connections", DEFAULT_MAX_CONNECTIONS),
            max_tries=data.get("max_tries", 0),
            max_concurrent=data.get("max_concurrent", DEFAULT_MAX_CONCURRENT),
            shutdown_after_finish=data.get("shutdown_after_finish", False),
            speed_limit=data.get("speed_limit", 0),
            auto_clear_completed=data.get("auto_clear_completed", False),
            theme=data.get("theme", "system"),
            default_download_path=data.get("default_download_path", str(DEFAULT_DOWNLOAD_PATH)),
            async_mode=data.get("async_mode", False),
        )


class DataStore:
    """
    Persistent data store with secure secret handling and thread-safety.
    
    The secret is stored in two places:
    1. keyring (primary, secure storage)
    2. settings (cached fallback in case keyring is unavailable)
    
    When reading: prefer keyring, fallback to settings.
    When writing: write to both keyring and settings.
    """

    PATH: Path = CONFIG_DIR / "data.json"
    BACKUP_PATH: Path = CONFIG_DIR / "data.json.bak"

    def __init__(self) -> None:
        self._lock = Lock()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        self.queues: List[Queue] = []
        self.settings: Settings = Settings()

        self._keyring_available = self._check_keyring()
        self.load()

        if not self._has_default_queue():
            self.queues.insert(0, Queue("Default", paused=True))
            self.save()

    def _check_keyring(self) -> bool:
        """
        Check if keyring is available and working.
        
        Returns:
            True if keyring is available and usable
        """
        try:
            # Try a simple operation to test keyring
            test_key = "__felfeldm_test"
            keyring.set_password(KEYRING_SERVICE, test_key, "test")
            result = keyring.get_password(KEYRING_SERVICE, test_key)
            keyring.delete_password(KEYRING_SERVICE, test_key)
            return result == "test"
        except Exception as e:
            logger.warning("Keyring is not available: %s", e)
            return False

    def _has_default_queue(self) -> bool:
        return any(q.name == "Default" for q in self.queues)

    def _load_from_json(self) -> Optional[Dict[str, Any]]:
        """Load data from JSON file with backup fallback."""
        if not self.PATH.exists():
            return None

        try:
            with self.PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to parse data.json: %s", e)
            # Try to load from backup
            if self.BACKUP_PATH.exists():
                logger.info("Attempting to load from backup...")
                try:
                    with self.BACKUP_PATH.open("r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception as be:
                    logger.error("Backup also failed: %s", be)
            return None
        except Exception as e:
            logger.error("Unexpected error loading data: %s", e)
            return None

    def _sync_secret_from_keyring(self) -> None:
        """
        Synchronize secret from keyring to settings.
        If keyring is unavailable, keep current value or load from settings.
        """
        if not self._keyring_available:
            logger.debug("Keyring unavailable, using settings secret")
            return

        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
            if secret is not None:
                if self.settings.aria2_secret != secret:
                    self.settings.aria2_secret = secret
                    logger.debug("Secret synced from keyring to settings")
            else:
                # No secret in keyring, save current secret to keyring if exists
                if self.settings.aria2_secret:
                    keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings.aria2_secret)
                    logger.debug("Secret synced from settings to keyring")
        except KeyringError as e:
            logger.warning("Keyring error during sync: %s", e)
            self._keyring_available = False
        except Exception as e:
            logger.warning("Unexpected keyring error: %s", e)

    def load(self) -> None:
        """Load data from disk with graceful error handling."""
        with self._lock:
            data = self._load_from_json()
            if data is None:
                logger.info("No existing data found, using defaults")
                return

            try:
                # Load queues
                self.queues = []
                for q_data in data.get("queues", []):
                    self.queues.append(Queue.from_dict(q_data))

                # Load settings
                settings_data = data.get("settings", {})
                self.settings = Settings.from_dict(settings_data)

                # Sync secret from keyring
                self._sync_secret_from_keyring()

                logger.info("Loaded %d queues successfully", len(self.queues))

            except Exception as e:
                logger.error("Failed to load data: %s", e)
                # Reset to defaults on error
                self.queues = []
                self.settings = Settings()

    def save(self) -> None:
        """Save data to disk with backup creation."""
        with self._lock:
            try:
                # Create backup of existing file
                if self.PATH.exists():
                    try:
                        import shutil
                        shutil.copy2(self.PATH, self.BACKUP_PATH)
                    except Exception as e:
                        logger.warning("Failed to create backup: %s", e)

                # Prepare data
                data = {
                    "queues": [q.to_dict() for q in self.queues],
                    "settings": self.settings.to_dict(),
                }

                # Save to keyring if available
                if self._keyring_available and self.settings.aria2_secret:
                    try:
                        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, self.settings.aria2_secret)
                    except Exception as e:
                        logger.warning("Failed to save secret to keyring: %s", e)
                        # Mark as unavailable to avoid repeated attempts
                        self._keyring_available = False

                # Save to JSON file
                with self.PATH.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                logger.debug("Data saved successfully")

            except Exception as e:
                logger.error("Failed to save data: %s", e)

    def get_secret(self) -> str:
        """
        Get the aria2 secret from keyring with fallback to settings.
        
        Returns:
            The secret string, or empty string if not found
        """
        if self._keyring_available:
            try:
                secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
                if secret is not None:
                    if self.settings.aria2_secret != secret:
                        self.settings.aria2_secret = secret
                    return secret
            except Exception as e:
                logger.warning("Failed to get secret from keyring: %s", e)
                self._keyring_available = False

        # Fallback to settings
        return self.settings.aria2_secret

    def set_secret(self, secret: str) -> None:
        """
        Save the aria2 secret to both keyring and settings.
        
        Args:
            secret: The secret string to save
        """
        self.settings.aria2_secret = secret

        if self._keyring_available and secret:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
                logger.debug("Secret saved to keyring")
            except Exception as e:
                logger.warning("Failed to save secret to keyring: %s", e)
                self._keyring_available = False

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
        for i, q in enumerate(self.queues):
            if q.name == name:
                return i
        return None

    def add_download_to_queue(self, queue_name: str, gid: str) -> None:
        """Add a GID to a specific queue."""
        q = self.get_queue(queue_name)
        if q and gid not in q.downloads:
            q.downloads.append(gid)
            self.save()

    def remove_download_from_queue(self, gid: str) -> None:
        """Remove a GID from all queues."""
        for q in self.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)
                self.save()
                break
