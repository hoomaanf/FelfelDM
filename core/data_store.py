# core/data_store.py
"""
Persistent data store for felfelDM.

Architecture:
  * Two independent, never-nested locks: `_lock` (queues/settings/proxies)
    and `_yt_lock` (youtube_downloads). No method holds both at once, so
    there is no lock-ordering deadlock to reason about.
  * Hot, high-frequency updates (YouTube progress ticks) are coalesced by
    a background flush thread instead of hitting disk synchronously.
    Meaningful state transitions (add/delete/status change) flush
    immediately so a crash never loses something that actually mattered.
  * All getters return deep copies — callers can never mutate internal
    state by holding onto a returned dict.
  * All writes are atomic (temp file + fsync + os.replace + best-effort
    directory fsync). There is no "best effort" non-atomic fallback path,
    because a torn write is worse than a stale-but-valid file.
"""

import os
import json
import shutil
import threading
import uuid
from copy import deepcopy
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from appdirs import user_config_dir

try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

from core.proxy_manager import ProxyConfig

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"

# How long we coalesce rapid youtube-download updates (progress ticks, etc.)
# before actually touching disk.
YT_FLUSH_INTERVAL = 1.5  # seconds

# Keep disk usage bounded even if the app runs for weeks and repeatedly
# hits a corrupted-config code path.
MAX_CORRUPTED_BACKUPS = 5

# Fields that belong on disk for a download record. Everything else
# (in-memory-only runtime fields the UI attaches, like `downloadSpeed`
# computed each poll, or `gid`) is intentionally dropped on save.
# NOTE: "status" MUST be in this list — main_window.py writes
# `q.downloads_info[gid]["status"] = ...` in dozens of places and relies
# on it surviving a save/load cycle to resume correctly after a restart.
_PERSISTED_DOWNLOAD_FIELDS = (
    "url",
    "name",
    "status",
    "totalLength",
    "completedLength",
    "files",
    "category",
    "download_type",
    "error_count",
    "errorMessage",
    "size_fetch_attempts",
    "real_path",
    "yt_options",
)


def _atomic_write_json(path: Path, payload: Any, indent: Optional[int] = 2) -> None:
    """
    Write JSON to `path` atomically and durably: write to a temp file in
    the same directory, fsync it, rename over the destination, then
    best-effort fsync the containing directory so the rename survives a
    crash too.
    """
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}-{threading.get_ident()}")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except (OSError, AttributeError):
        pass  # not available/meaningful on every platform (e.g. Windows)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Queue:
    def __init__(
        self,
        name,
        max_concurrent=3,
        save_path="",
        schedule_enabled=False,
        schedule_start=None,
        schedule_end=None,
        days=None,
        paused=True,
        proxy_config=None,
        speed_limit=0,
        manually_paused = False
    ):
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or os.path.expanduser("~/Downloads")
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads: List[str] = []
        self.downloads_info: Dict[str, Dict] = {}
        self.paused = paused
        self.proxy_config = proxy_config
        self.speed_limit = speed_limit
        self.error_count = 0
        self.manually_paused = manually_paused

    def to_dict(self) -> Dict:
        proxy_dict = None
        if self.proxy_config:
            if isinstance(self.proxy_config, ProxyConfig):
                proxy_dict = self.proxy_config.to_dict()
            else:
                proxy_dict = self.proxy_config

        downloads_info = {}
        for gid in self.downloads:
            info = self.downloads_info.get(gid)
            if info is None:
                continue
            downloads_info[gid] = {
                field: info[field]
                for field in _PERSISTED_DOWNLOAD_FIELDS
                if field in info
            }
            # Always persist a status even if the caller never set one,
            # so a restart doesn't silently forget it defaulted to "waiting".
            downloads_info[gid].setdefault("status", info.get("status", "waiting"))

        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "save_path": self.save_path,
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": self.schedule_start.strftime("%H:%M"),
            "schedule_end": self.schedule_end.strftime("%H:%M"),
            "days": self.days,
            "downloads": self.downloads,
            "downloads_info": downloads_info,
            "paused": self.paused,
            "proxy_config": proxy_dict,
            "speed_limit": self.speed_limit,
            "error_count": self.error_count,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Queue":
        name = d.get("name", "Default")
        q = cls(name)
        q.max_concurrent = max(1, _safe_int(d.get("max_concurrent"), 3))
        q.save_path = d.get("save_path") or os.path.expanduser("~/Downloads")
        q.schedule_enabled = bool(d.get("schedule_enabled", False))
        q.paused = bool(d.get("paused", True))

        st = str(d.get("schedule_start", "00:00")).split(":")
        en = str(d.get("schedule_end", "23:59")).split(":")
        try:
            q.schedule_start = dtime(int(st[0]), int(st[1]))
            q.schedule_end = dtime(int(en[0]), int(en[1]))
        except (ValueError, IndexError):
            q.schedule_start = dtime(0, 0)
            q.schedule_end = dtime(23, 59)

        days = d.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.days = [x for x in days if isinstance(x, int) and 0 <= x <= 6] or [
            0,
            1,
            2,
            3,
            4,
            5,
            6,
        ]
        q.downloads = list(d.get("downloads", []))
        q.downloads_info = dict(d.get("downloads_info", {}))
        q.speed_limit = max(0, _safe_int(d.get("speed_limit"), 0))
        q.error_count = max(0, _safe_int(d.get("error_count"), 0))

        proxy_config = d.get("proxy_config")
        if proxy_config:
            try:
                q.proxy_config = ProxyConfig.from_dict(proxy_config)
            except Exception as e:
                print(f"⚠️ Error loading proxy config for queue {name}: {e}")
                q.proxy_config = None
        else:
            q.proxy_config = None
        return q

    def is_scheduled_now(self) -> bool:
        if not self.schedule_enabled:
            return True
        now = datetime.now()
        weekday = now.weekday()
        t = now.time().replace(second=0, microsecond=0)
        start, end = self.schedule_start, self.schedule_end

        if start <= end:
            return weekday in self.days and start <= t <= end

        # Overnight window (e.g. 22:00 -> 06:00). The window "belongs" to
        # the day it starts on, so the post-midnight portion must check
        # *yesterday's* weekday, not today's.
        if t >= start:
            return weekday in self.days
        if t <= end:
            return (weekday - 1) % 7 in self.days
        return False

    def get_next_schedule_time(self) -> Optional[datetime]:
        """
        Return the next datetime this schedule will (re-)activate, or None
        if the schedule is disabled. If the window is active right now,
        returns None — "next start" isn't a meaningful concept while
        already inside the window; callers should check `is_scheduled_now()`
        first if they need to distinguish "active" from "waiting".
        """
        if not self.schedule_enabled:
            return None
        if self.is_scheduled_now():
            return None

        now = datetime.now()
        weekday = now.weekday()
        t = now.time().replace(second=0, microsecond=0)

        # Today, if today is a scheduled day and start hasn't happened yet.
        if weekday in self.days and t < self.schedule_start:
            return datetime.combine(now.date(), self.schedule_start)

        # Otherwise walk forward day by day (starting from today, i=0, so
        # an overnight schedule that starts later tonight is still found).
        for i in range(0, 8):
            candidate_day = (weekday + i) % 7
            if candidate_day in self.days:
                candidate_date = now.date() + timedelta(days=i)
                candidate_dt = datetime.combine(candidate_date, self.schedule_start)
                if candidate_dt > now:
                    return candidate_dt
        return None


class DataStore:
    def __init__(self):
        self.config_dir = Path(user_config_dir("felfelDM"))
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.data_file = self.config_dir / "data.json"
        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)
        self.youtube_downloads_file = self.config_dir / "youtube_downloads.json"

        # Never acquire both locks at once — see module docstring.
        self._lock = threading.Lock()
        self._yt_lock = threading.Lock()

        self.queues: List[Queue] = []
        self.settings = self._get_default_settings()
        self.download_proxies: Dict[str, Any] = {}
        self.youtube_downloads: Dict[str, dict] = {}

        # Must exist before load(), because load() can call save() (e.g. on
        # a fresh install with no config file yet), and save() calls
        # flush(), which touches these.
        self._yt_dirty = threading.Event()
        self._yt_stop = threading.Event()

        self.load()

        self._yt_thread = threading.Thread(
            target=self._yt_flush_loop, name="felfelDM-yt-writer", daemon=True
        )
        self._yt_thread.start()

    # ------------------------------------------------------------------
    def _get_default_settings(self) -> Dict:
        return {
            "aria2_host": "http://localhost",
            "aria2_port": 6800,
            "aria2_secret": "",
            "connections": 8,
            "max_tries": 5,
            "max_concurrent": 5,
            "shutdown_after_finish": False,
            "speed_limit": 0,
            "auto_clear_completed": False,
            "theme": "auto",
            "run_as_service": False,
            "proxy_settings": {"global": None, "queues": {}},
        }

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.data_file.exists():
            print("📁 No config file found, using defaults")
            self.queues = [Queue("Default", paused=True)]
            self.save()
        else:
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Isolate each queue's parsing: one corrupted queue entry
                # should not discard every other valid queue.
                queues = []
                for q_data in data.get("queues", []):
                    if not isinstance(q_data, dict):
                        continue
                    try:
                        queues.append(Queue.from_dict(q_data))
                    except Exception as e:
                        print(f"⚠️ Error loading queue, skipping it: {e}")

                settings = self._get_default_settings()
                settings.update(data.get("settings", {}))

                with self._lock:
                    self.queues = queues
                    self.settings = settings
                    self.download_proxies = data.get("download_proxies", {})

            except json.JSONDecodeError as e:
                print(f"⚠️ Config file corrupted: {e}")
                self._backup_corrupted_file()
                with self._lock:
                    self.queues = [Queue("Default", paused=True)]
                    self.settings = self._get_default_settings()
                    self.download_proxies = {}
                self.save()

            except Exception as e:
                print(f"⚠️ Error loading data: {e}")
                self._backup_corrupted_file()
                with self._lock:
                    if not self.queues:
                        self.queues = [Queue("Default", paused=True)]
                    self.download_proxies = {}

        self._load_secret()

        with self._lock:
            if not self.queues:
                self.queues = [Queue("Default", paused=True)]

        self._load_youtube_downloads()

    def _load_secret(self) -> None:
        """Load secret from keyring, falling back to a plaintext file."""
        if KEYRING_AVAILABLE:
            try:
                secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
                if secret:
                    with self._lock:
                        self.settings["aria2_secret"] = secret
                    return
            except Exception as e:
                print(f"⚠️ Could not load secret from keyring: {e}")

        secret_file = self.config_dir / "secret.txt"
        if secret_file.exists():
            try:
                with open(secret_file, "r", encoding="utf-8") as f:
                    secret = f.read().strip()
                with self._lock:
                    self.settings["aria2_secret"] = secret
            except Exception as e:
                print(f"⚠️ Could not read fallback secret file: {e}")

    def _save_secret(self, secret: str) -> bool:
        """
        Save the secret via keyring, falling back to a chmod-600 plaintext
        file whenever keyring is unavailable OR fails. The fallback must
        run in both cases — attempting it only when keyring already
        failed, and never otherwise, means the secret is silently lost
        forever on any machine without a working keyring backend.
        """
        if not secret:
            return False

        if KEYRING_AVAILABLE:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
                return True
            except Exception as e:
                print(f"⚠️ Could not save secret to keyring: {e}")

        try:
            secret_file = self.config_dir / "secret.txt"
            with open(secret_file, "w", encoding="utf-8") as f:
                f.write(secret)
            os.chmod(secret_file, 0o600)
            return True
        except Exception as e:
            print(f"⚠️ Could not persist secret to fallback file: {e}")
            return False

    def _backup_corrupted_file(self) -> None:
        if not self.data_file.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"felfeldm_corrupted_{timestamp}.json"
        try:
            shutil.copy2(self.data_file, backup_file)
            print(f"📁 Corrupted file backed up to: {backup_file}")
            self._prune_old_backups()
        except Exception as e:
            print(f"⚠️ Could not backup corrupted file: {e}")

    def _prune_old_backups(self) -> None:
        try:
            backups = sorted(self.backup_dir.glob("felfeldm_corrupted_*.json"))
            excess = len(backups) - MAX_CORRUPTED_BACKUPS
            for old in backups[: max(0, excess)]:
                old.unlink(missing_ok=True)
        except Exception as e:
            print(f"⚠️ Could not prune old corrupted backups: {e}")

    # ------------------------------------------------------------------
    # Main config save
    # ------------------------------------------------------------------
    def save(self) -> None:
        with self._lock:
            secret = self.settings.pop("aria2_secret", "")
            payload = {
                "queues": [q.to_dict() for q in self.queues],
                "settings": deepcopy(self.settings),
                "download_proxies": deepcopy(self.download_proxies),
            }
            self.settings["aria2_secret"] = secret

        if secret:
            self._save_secret(secret)

        try:
            _atomic_write_json(self.data_file, payload)
        except Exception as e:
            # No non-atomic fallback: a torn write would corrupt the last
            # known-good config, which is worse than leaving it stale.
            print(f"⚠️ Error saving data (previous config on disk is unchanged): {e}")

        self.flush()

    # ------------------------------------------------------------------
    # YouTube downloads: hot path, background-flushed
    # ------------------------------------------------------------------
    def _load_youtube_downloads(self) -> None:
        if not self.youtube_downloads_file.exists():
            print("📁 No YouTube downloads file found")
            self.youtube_downloads = {}
            return
        try:
            with open(self.youtube_downloads_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._yt_lock:
                self.youtube_downloads = data.get("downloads", {})
            print(f"📁 Loaded {len(self.youtube_downloads)} YouTube downloads")
        except Exception as e:
            print(f"⚠️ Error loading YouTube downloads: {e}")
            self.youtube_downloads = {}

    def _flush_youtube_downloads(self) -> None:
        with self._yt_lock:
            snapshot = deepcopy(self.youtube_downloads)
        try:
            _atomic_write_json(
                self.youtube_downloads_file, {"downloads": snapshot}, indent=None
            )
        except Exception as e:
            print(f"⚠️ Error saving YouTube downloads: {e}")

    def _yt_flush_loop(self) -> None:
        while True:
            stop_requested = self._yt_stop.wait(YT_FLUSH_INTERVAL)
            if self._yt_dirty.is_set():
                self._yt_dirty.clear()
                self._flush_youtube_downloads()
            if stop_requested:
                break

    def flush(self) -> None:
        """Force an immediate write of any pending youtube_downloads changes."""
        self._yt_dirty.clear()
        self._flush_youtube_downloads()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Stop the background writer deterministically and flush pending state."""
        self._yt_stop.set()
        self._yt_thread.join(timeout=timeout)
        self._flush_youtube_downloads()

    def add_youtube_download(self, download_data: dict) -> str:
        download_id = download_data.get("id") or str(uuid.uuid4())
        record = deepcopy(download_data)
        record["id"] = download_id
        with self._yt_lock:
            self.youtube_downloads[download_id] = record
        self._flush_youtube_downloads()
        return download_id

    def get_youtube_download(self, download_id: str) -> Optional[dict]:
        with self._yt_lock:
            d = self.youtube_downloads.get(download_id)
            return deepcopy(d) if d is not None else None

    def get_all_youtube_downloads(self) -> List[dict]:
        with self._yt_lock:
            return [deepcopy(d) for d in self.youtube_downloads.values()]

    def get_youtube_downloads_by_status(self, status: str) -> List[dict]:
        with self._yt_lock:
            return [
                deepcopy(d)
                for d in self.youtube_downloads.values()
                if d.get("status") == status
            ]

    def get_youtube_downloads_by_queue(self, queue_id: str) -> List[dict]:
        with self._yt_lock:
            return [
                deepcopy(d)
                for d in self.youtube_downloads.values()
                if d.get("queue_id") == queue_id
            ]

    def update_youtube_download(
        self, download_id: str, updates: dict, flush: bool = True
    ) -> bool:
        with self._yt_lock:
            if download_id not in self.youtube_downloads:
                return False
            self.youtube_downloads[download_id].update(deepcopy(updates))
        if flush:
            self._flush_youtube_downloads()
        else:
            self._yt_dirty.set()
        return True

    def update_youtube_status(self, download_id: str, status: str) -> bool:
        return self.update_youtube_download(download_id, {"status": status}, flush=True)

    def update_youtube_progress(self, download_id: str, progress: int) -> bool:
        # Called many times per second per active download — coalesced,
        # not flushed synchronously.
        return self.update_youtube_download(
            download_id, {"progress": progress}, flush=False
        )

    def delete_youtube_download(self, download_id: str) -> bool:
        with self._yt_lock:
            if download_id not in self.youtube_downloads:
                return False
            del self.youtube_downloads[download_id]
        self._flush_youtube_downloads()
        return True

    def clear_completed_youtube_downloads(self) -> int:
        with self._yt_lock:
            completed_ids = [
                d_id
                for d_id, d in self.youtube_downloads.items()
                if d.get("status") in ("completed", "cancelled")
            ]
            for d_id in completed_ids:
                del self.youtube_downloads[d_id]
        if completed_ids:
            self._flush_youtube_downloads()
        return len(completed_ids)

    def get_youtube_downloads_count(self) -> int:
        with self._yt_lock:
            return len(self.youtube_downloads)

    def get_youtube_downloads_count_by_status(self, status: str) -> int:
        with self._yt_lock:
            return sum(
                1 for d in self.youtube_downloads.values() if d.get("status") == status
            )

    def get_youtube_downloads_info_for_display(self) -> List[dict]:
        with self._yt_lock:
            items = list(self.youtube_downloads.items())

        display_list = []
        for d_id, d in items:
            yt_options = d.get("yt_options", {})
            display_list.append(
                {
                    "id": d_id,
                    "url": d.get("url", ""),
                    "title": yt_options.get("title", d.get("url", "")),
                    "status": d.get("status", "pending"),
                    "progress": d.get("progress", 0),
                    "speed": d.get("speed", ""),
                    "eta": d.get("eta", ""),
                    "save_path": d.get("save_path", ""),
                    "queue_id": d.get("queue_id", ""),
                    "created_at": d.get("created_at", ""),
                    "completed_at": d.get("completed_at"),
                    "error_message": d.get("error_message", ""),
                    "quality": yt_options.get("quality", "best"),
                    "format": yt_options.get("format", "video"),
                    "download_type": "youtube",
                }
            )
        return display_list
