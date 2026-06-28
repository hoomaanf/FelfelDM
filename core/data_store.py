# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0
"""Data persistence with priority queues and keyring integration."""

import json
import logging
import uuid
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from threading import Lock

from appdirs import user_config_dir
import keyring
from keyring.errors import KeyringError, NoKeyringError

logger: logging.Logger = logging.getLogger(__name__)

_SECRET_SUFFIX = uuid.uuid4().hex[:8]
KEYRING_SERVICE: str = f"felfelDM_{_SECRET_SUFFIX}"
KEYRING_ARIA2_SECRET: str = "aria2_secret"


@dataclass
class Queue:
    name: str
    max_concurrent: int = 3
    save_path: str = ""
    schedule_enabled: bool = False
    schedule_start: dtime = field(default_factory=lambda: dtime(0, 0))
    schedule_end: dtime = field(default_factory=lambda: dtime(23, 59))
    days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    downloads: List[str] = field(default_factory=list)
    paused: bool = True
    priority: int = 0  # 0 = highest, higher = lower

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
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Queue":
        q = cls(name=data.get("name", "Default"))
        q.max_concurrent = data.get("max_concurrent", 3)
        q.save_path = data.get("save_path", str(Path.home() / "Downloads"))
        q.schedule_enabled = data.get("schedule_enabled", False)
        try:
            st = data.get("schedule_start", "00:00").split(":")
            q.schedule_start = dtime(int(st[0]), int(st[1]))
        except Exception:
            q.schedule_start = dtime(0, 0)
        try:
            en = data.get("schedule_end", "23:59").split(":")
            q.schedule_end = dtime(int(en[0]), int(en[1]))
        except Exception:
            q.schedule_end = dtime(23, 59)
        q.days = data.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(data.get("downloads", []))
        q.paused = data.get("paused", True)
        q.priority = data.get("priority", 0)
        return q

    def is_scheduled_now(self) -> bool:
        if not self.schedule_enabled:
            return True
        now = datetime.now()
        if now.weekday() not in self.days:
            return False
        current_time = now.time().replace(second=0, microsecond=0)
        start, end = self.schedule_start, self.schedule_end
        return start <= current_time <= end if start <= end else current_time >= start or current_time <= end


class DataStore:
    CONFIG_DIR: Path = Path(user_config_dir("felfelDM"))
    DATA_FILE: Path = CONFIG_DIR / "data.json"

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {}
        self.settings: Dict[str, Any] = {}
        self.queues: Dict[str, Queue] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.DATA_FILE.exists():
                self._init_defaults()
                return
            try:
                with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self.settings = self._data.get("settings", {})
                queues_data = self._data.get("queues", {})
                self.queues = {name: Queue.from_dict(qdata) for name, qdata in queues_data.items()}
                logger.info("Loaded %d queues", len(self.queues))
            except Exception as e:
                logger.error("Load failed: %s", e)
                self._init_defaults()

    def _init_defaults(self) -> None:
        self.settings = {
            "aria2_host": "https://127.0.0.1",
            "aria2_port": 6800,
            "aria2_timeout": 5,
            "poll_interval": 10000,
            "max_connections": 16,
            "max_downloads": 5,
        }
        self.queues = {
            "default": Queue(name="default", max_concurrent=3, save_path=str(Path.home() / "Downloads"), paused=False)
        }
        self._save()

    def _save(self) -> None:
        with self._lock:
            try:
                data = {
                    "settings": self.settings,
                    "queues": {name: q.to_dict() for name, q in self.queues.items()},
                    "version": "3.0",
                }
                with open(self.DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.DATA_FILE.chmod(0o600)
            except Exception as e:
                logger.error("Save failed: %s", e)

    def reload(self) -> None:
        self._load()

    def get_queues(self) -> Dict[str, Queue]:
        with self._lock:
            return dict(self.queues)

    def get_queue(self, name: str) -> Optional[Queue]:
        with self._lock:
            return self.queues.get(name)

    def add_queue(self, queue: Queue) -> None:
        with self._lock:
            self.queues[queue.name] = queue
            self._save()

    def remove_queue(self, name: str) -> bool:
        with self._lock:
            if name in self.queues:
                del self.queues[name]
                self._save()
                return True
            return False

    def add_gid_to_queue(self, queue_name: str, gid: str) -> None:
        with self._lock:
            if queue_name in self.queues and gid not in self.queues[queue_name].downloads:
                self.queues[queue_name].downloads.append(gid)
                self._save()

    def remove_gid(self, gid: str) -> None:
        with self._lock:
            for queue in self.queues.values():
                if gid in queue.downloads:
                    queue.downloads.remove(gid)
            self._save()

    def get_all_gids(self) -> List[str]:
        with self._lock:
            gids = []
            for queue in self.queues.values():
                gids.extend(queue.downloads)
            return list(set(gids))

    def get_gids_by_queue(self, queue_name: str) -> List[str]:
        with self._lock:
            queue = self.queues.get(queue_name)
            return queue.downloads if queue else []

    # Keyring helpers
    def get_aria2_secret(self) -> str:
        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_ARIA2_SECRET)
            if secret:
                return secret
        except Exception:
            pass
        return self.settings.get("aria2_secret", "")

    def set_aria2_secret(self, secret: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ARIA2_SECRET, secret)
        except Exception as e:
            logger.warning("Keyring failed: %s", e)
            self.settings["aria2_secret"] = secret
            self._save()

    def get_cookies(self, gid: str) -> Optional[str]:
        try:
            return keyring.get_password(KEYRING_SERVICE, f"cookies_{gid}")
        except Exception:
            return None

    def set_cookies(self, gid: str, cookies: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, f"cookies_{gid}", cookies)
        except Exception as e:
            logger.warning("Failed to store cookies: %s", e)

    def get_headers(self, gid: str) -> Optional[str]:
        try:
            return keyring.get_password(KEYRING_SERVICE, f"headers_{gid}")
        except Exception:
            return None

    def set_headers(self, gid: str, headers: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, f"headers_{gid}", headers)
        except Exception as e:
            logger.warning("Failed to store headers: %s", e)
