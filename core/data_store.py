# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0

"""
Data persistence layer with encryption for sensitive data.
"""

import os
import json
import logging
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Optional, Dict, Any, Set, cast
from dataclasses import dataclass, field, asdict
from threading import Lock

from appdirs import user_config_dir
import keyring
from keyring.errors import KeyringError, NoKeyringError

logger: logging.Logger = logging.getLogger(__name__)

KEYRING_SERVICE: str = "felfelDM"
KEYRING_ARIA2_SECRET: str = "aria2_secret"
KEYRING_COOKIES: str = "cookies"
KEYRING_HEADERS: str = "headers"


@dataclass
class Queue:
    """Represents a download queue."""
    name: str
    max_concurrent: int = 3
    save_path: str = ""
    schedule_enabled: bool = False
    schedule_start: dtime = field(default_factory=lambda: dtime(0, 0))
    schedule_end: dtime = field(default_factory=lambda: dtime(23, 59))
    days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    downloads: List[str] = field(default_factory=list)  # GIDs
    paused: bool = True

    def __post_init__(self) -> None:
        if not self.save_path:
            self.save_path = str(Path.home() / "Downloads")

    def to_dict(self) -> Dict[str, Any]:
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
    def from_dict(cls, data: Dict[str, Any]) -> "Queue":
        name = data.get("name", "Default")
        q = cls(name=name)
        q.max_concurrent = data.get("max_concurrent", 3)
        q.save_path = data.get("save_path", str(Path.home() / "Downloads"))
        q.schedule_enabled = data.get("schedule_enabled", False)
        try:
            st = data.get("schedule_start", "00:00").split(":")
            if len(st) == 2:
                q.schedule_start = dtime(int(st[0]), int(st[1]))
        except (ValueError, TypeError):
            q.schedule_start = dtime(0, 0)
        try:
            en = data.get("schedule_end", "23:59").split(":")
            if len(en) == 2:
                q.schedule_end = dtime(int(en[0]), int(en[1]))
        except (ValueError, TypeError):
            q.schedule_end = dtime(23, 59)
        q.days = data.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(data.get("downloads", []))
        q.paused = data.get("paused", True)
        return q

    def is_scheduled_now(self) -> bool:
        if not self.schedule_enabled:
            return True
        now = datetime.now()
        if now.weekday() not in self.days:
            return False
        current_time = now.time().replace(second=0, microsecond=0)
        start = self.schedule_start
        end = self.schedule_end
        if start <= end:
            return start <= current_time <= end
        return current_time >= start or current_time <= end


class DataStore:
    """
    Manages persistent storage with encryption for sensitive fields.
    Thread-safe using a lock for all read/write operations.
    """

    CONFIG_DIR: Path = Path(user_config_dir("felfelDM"))
    PATH: Path = CONFIG_DIR / "data.json"
    KEY_FILE: Path = CONFIG_DIR / ".key"

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self._ensure_config_dir()
        self.queues: List[Queue] = []
        self.settings: Dict[str, Any] = {
            "aria2_host": "http://127.0.0.1",
            "aria2_port": 6800,
            "connections": 16,
            "max_tries": 0,
            "max_concurrent": 5,
            "shutdown_after_finish": False,
            "speed_limit": 0,
            "auto_clear_completed": False,
            "aria2_timeout": 5,
            "poll_interval": 5000,
            "disk_cache": "128M",
            "adjust_split": True,
            "split": 16,
        }
        self._aria2_secret: Optional[str] = None
        self._load()

        if not self.queues:
            self.queues = [Queue(name="Default", paused=True)]

    def _ensure_config_dir(self) -> None:
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    def _get_keyring_secret(self, key: str) -> str:
        try:
            secret = keyring.get_password(KEYRING_SERVICE, key)
            return secret if secret is not None else ""
        except Exception as e:
            logger.error("Keyring error for %s: %s", key, e)
            return ""

    def _set_keyring_secret(self, key: str, value: str) -> bool:
        try:
            if not value:
                try:
                    keyring.delete_password(KEYRING_SERVICE, key)
                except:
                    pass
                return True
            keyring.set_password(KEYRING_SERVICE, key, value)
            return True
        except Exception as e:
            logger.error("Failed to save %s to keyring: %s", key, e)
            return False

    def get_aria2_secret(self) -> str:
        with self._lock:
            if self._aria2_secret is None:
                self._aria2_secret = self._get_keyring_secret(KEYRING_ARIA2_SECRET)
            return self._aria2_secret

    def set_aria2_secret(self, secret: str) -> bool:
        with self._lock:
            success = self._set_keyring_secret(KEYRING_ARIA2_SECRET, secret)
            if success:
                self._aria2_secret = secret
                self._save()
            return success

    def get_cookies(self) -> str:
        with self._lock:
            return self._get_keyring_secret(KEYRING_COOKIES)

    def set_cookies(self, cookies: str) -> bool:
        with self._lock:
            return self._set_keyring_secret(KEYRING_COOKIES, cookies)

    def get_headers(self) -> str:
        with self._lock:
            return self._get_keyring_secret(KEYRING_HEADERS)

    def set_headers(self, headers: str) -> bool:
        with self._lock:
            return self._set_keyring_secret(KEYRING_HEADERS, headers)

    def _load(self) -> None:
        try:
            with self.PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
            self.queues = [Queue.from_dict(q) for q in data.get("queues", [])]
            settings_data = data.get("settings", {})
            self.settings.update(settings_data)
            self.settings.setdefault("aria2_timeout", 5)
            self.settings.setdefault("poll_interval", 5000)
            self.settings.setdefault("disk_cache", "128M")
            self.settings.setdefault("adjust_split", True)
            self.settings.setdefault("split", 16)
        except FileNotFoundError:
            logger.info("No existing data file found, using defaults")
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in data file: %s", e)
        except Exception as e:
            logger.error("Unexpected error loading data: %s", e)

    def _save(self) -> None:
        try:
            data = {
                "queues": [q.to_dict() for q in self.queues],
                "settings": self.settings,
            }
            with self.PATH.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("Error saving data: %s", e)

    def save(self) -> None:
        with self._lock:
            self._save()

    def add_gid_to_queue(self, queue_name: str, gid: str) -> None:
        with self._lock:
            for q in self.queues:
                if q.name == queue_name:
                    if gid not in q.downloads:
                        q.downloads.append(gid)
                        self._save()
                    break

    def remove_gid_from_queue(self, gid: str) -> None:
        with self._lock:
            for q in self.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                    self._save()
                    break
