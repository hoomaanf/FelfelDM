# core/data_store.py

import os
import json
import shutil
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, List, Optional, Any
import uuid


def get_config_dir(appname: str = "felfelDM") -> str:
    """Get XDG config directory (Linux/Unix)"""

    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(config_home, appname)


try:
    import keyring

    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"


class Queue:
    def __init__(
        self,
        name: str,
        max_concurrent: int = 3,
        save_path: str = "",
        schedule_enabled: bool = False,
        schedule_start: Optional[dtime] = None,
        schedule_end: Optional[dtime] = None,
        days: Optional[List[int]] = None,
        paused: bool = True,
        proxy_config: Optional[Any] = None,
        speed_limit: int = 0,
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

    def to_dict(self) -> Dict:
        proxy_dict = None
        if self.proxy_config:
            from core.proxy_manager import ProxyConfig

            if isinstance(self.proxy_config, ProxyConfig):
                proxy_dict = self.proxy_config.to_dict()
            else:
                proxy_dict = self.proxy_config

        downloads_info = {}
        for gid in self.downloads:
            if gid in self.downloads_info:
                downloads_info[gid] = self.downloads_info[gid]

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
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Queue":
        name = d.get("name", "Default")
        q = cls(name)
        q.max_concurrent = d.get("max_concurrent", 3)
        q.save_path = d.get("save_path", os.path.expanduser("~/Downloads"))
        q.schedule_enabled = d.get("schedule_enabled", False)
        q.paused = d.get("paused", True)

        st = d.get("schedule_start", "00:00").split(":")
        en = d.get("schedule_end", "23:59").split(":")
        try:
            q.schedule_start = dtime(int(st[0]), int(st[1]))
            q.schedule_end = dtime(int(en[0]), int(en[1]))
        except (ValueError, IndexError):
            q.schedule_start = dtime(0, 0)
            q.schedule_end = dtime(23, 59)

        q.days = d.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(d.get("downloads", []))
        q.downloads_info = d.get("downloads_info", {})
        q.speed_limit = d.get("speed_limit", 0)

        proxy_config = d.get("proxy_config")
        if proxy_config:
            try:
                from core.proxy_manager import ProxyConfig

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
        if now.weekday() not in self.days:
            return False
        t = now.time().replace(second=0, microsecond=0)
        start = self.schedule_start
        end = self.schedule_end
        if start <= end:
            return start <= t <= end
        else:
            return t >= start or t <= end

    def get_next_schedule_time(self):
        if not self.schedule_enabled:
            return None
        from datetime import datetime, timedelta

        now = datetime.now()
        current_time = now.time()
        current_day = now.weekday()
        start_time = self.schedule_start

        if current_day in self.days and start_time > current_time:
            return datetime.combine(now.date(), start_time)

        for i in range(1, 8):
            next_day = (current_day + i) % 7
            if next_day in self.days:
                days_ahead = i
                if next_day <= current_day:
                    days_ahead = 7 - current_day + next_day
                next_date = now.date() + timedelta(days=days_ahead)
                return datetime.combine(next_date, start_time)
        return None


class DataStore:
    def __init__(self):

        config_dir = get_config_dir("felfelDM")
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.data_file = self.config_dir / "data.json"
        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)

        self.queues: List[Queue] = []
        self.settings = self._get_default_settings()
        self.download_proxies: Dict[str, Any] = {}

        self.youtube_downloads_file = self.config_dir / "youtube_downloads.json"
        self.youtube_downloads: Dict[str, dict] = {}

        self.load()

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

    def load(self):
        if not self.data_file.exists():
            print("📁 No config file found, using defaults")
            self.queues = [Queue("Default", paused=True)]
            self.save()
            return

        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.queues = []
            for q_data in data.get("queues", []):
                if isinstance(q_data, dict):
                    try:
                        self.queues.append(Queue.from_dict(q_data))
                    except Exception as e:
                        print(f"⚠️ Error loading queue: {e}")

            self.settings.update(data.get("settings", {}))
            self.download_proxies = data.get("download_proxies", {})

            for key, value in self._get_default_settings().items():
                if key not in self.settings:
                    self.settings[key] = value

        except (json.JSONDecodeError, ValueError) as e:
            print(f"⚠️ Config file corrupted: {e}")
            self._backup_corrupted_file()
            self.queues = [Queue("Default", paused=True)]
            self.settings = self._get_default_settings()
            self.download_proxies = {}
            self.save()

        except Exception as e:
            print(f"⚠️ Error loading data: {e}")
            self._backup_corrupted_file()
            self.queues = [Queue("Default", paused=True)]
            self.download_proxies = {}

        self._load_secret()

        if not self.queues:
            self.queues = [Queue("Default", paused=True)]

        self._load_youtube_downloads()

    def _load_secret(self):
        """Load secret from keyring or fallback to file"""
        if KEYRING_AVAILABLE:
            try:
                secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
                if secret:
                    self.settings["aria2_secret"] = secret
                    return
            except Exception as e:
                print(f"⚠️ Could not load secret from keyring: {e}")

        secret_file = self.config_dir / "secret.txt"
        if secret_file.exists():
            try:
                with open(secret_file, "r") as f:
                    self.settings["aria2_secret"] = f.read().strip()
            except:
                pass

    def _save_secret(self, secret: str):
        """Save secret to keyring or fallback to file"""
        if KEYRING_AVAILABLE and secret:
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
                return True
            except Exception as e:
                print(f"⚠️ Could not save secret to keyring: {e}")

                try:
                    secret_file = self.config_dir / "secret.txt"
                    with open(secret_file, "w") as f:
                        f.write(secret)
                    os.chmod(secret_file, 0o600)
                    return True
                except:
                    pass
        return False

    def _load_youtube_downloads(self):
        if not self.youtube_downloads_file.exists():
            self.youtube_downloads = {}
            return

        try:
            with open(self.youtube_downloads_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.youtube_downloads = data.get("downloads", {})
                print(f"📁 Loaded {len(self.youtube_downloads)} YouTube downloads")
        except Exception as e:
            print(f"⚠️ Error loading YouTube downloads: {e}")
            self.youtube_downloads = {}

    def _save_youtube_downloads(self):
        try:
            temp_file = self.youtube_downloads_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"downloads": self.youtube_downloads},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.youtube_downloads_file)
        except Exception as e:
            print(f"⚠️ Error saving YouTube downloads: {e}")

    def _backup_corrupted_file(self):
        if not self.data_file.exists():
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.backup_dir / f"felfeldm_corrupted_{timestamp}.json"
        try:
            shutil.copy2(self.data_file, backup_file)
            print(f"📁 Corrupted file backed up to: {backup_file}")
        except Exception as e:
            print(f"⚠️ Could not backup corrupted file: {e}")

    def save(self):
        secret = self.settings.pop("aria2_secret", "")
        if secret:
            self._save_secret(secret)

        try:
            temp_file = self.data_file.with_suffix(".json.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "queues": [q.to_dict() for q in self.queues],
                        "settings": self.settings,
                        "download_proxies": self.download_proxies,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, self.data_file)

        except Exception as e:
            print(f"⚠️ Error saving data: {e}")
            try:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "queues": [q.to_dict() for q in self.queues],
                            "settings": self.settings,
                            "download_proxies": self.download_proxies,
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
            except:
                print("❌ Failed to save data!")

        self.settings["aria2_secret"] = secret
        self._save_youtube_downloads()

    def add_youtube_download(self, download_data: dict) -> str:
        download_id = download_data.get("id")
        if not download_id:
            download_id = str(uuid.uuid4())
            download_data["id"] = download_id
        self.youtube_downloads[download_id] = download_data
        self._save_youtube_downloads()
        return download_id

    def get_youtube_download(self, download_id: str) -> Optional[dict]:
        return self.youtube_downloads.get(download_id)

    def get_all_youtube_downloads(self) -> List[dict]:
        return list(self.youtube_downloads.values())

    def get_youtube_downloads_by_status(self, status: str) -> List[dict]:
        return [d for d in self.youtube_downloads.values() if d.get("status") == status]

    def get_youtube_downloads_by_queue(self, queue_id: str) -> List[dict]:
        return [
            d for d in self.youtube_downloads.values() if d.get("queue_id") == queue_id
        ]

    def update_youtube_download(self, download_id: str, updates: dict) -> bool:
        if download_id not in self.youtube_downloads:
            return False
        self.youtube_downloads[download_id].update(updates)
        self._save_youtube_downloads()
        return True

    def update_youtube_status(self, download_id: str, status: str) -> bool:
        return self.update_youtube_download(download_id, {"status": status})

    def update_youtube_progress(self, download_id: str, progress: int) -> bool:
        return self.update_youtube_download(download_id, {"progress": progress})

    def delete_youtube_download(self, download_id: str) -> bool:
        if download_id not in self.youtube_downloads:
            return False
        del self.youtube_downloads[download_id]
        self._save_youtube_downloads()
        return True

    def clear_completed_youtube_downloads(self) -> int:
        completed_ids = [
            d_id
            for d_id, d in self.youtube_downloads.items()
            if d.get("status") in ["completed", "cancelled"]
        ]
        for d_id in completed_ids:
            del self.youtube_downloads[d_id]
        if completed_ids:
            self._save_youtube_downloads()
        return len(completed_ids)

    def get_youtube_downloads_count(self) -> int:
        return len(self.youtube_downloads)

    def get_youtube_downloads_count_by_status(self, status: str) -> int:
        return len(self.get_youtube_downloads_by_status(status))

    def get_youtube_downloads_info_for_display(self) -> List[dict]:
        display_list = []
        for d_id, d in self.youtube_downloads.items():
            display_list.append(
                {
                    "id": d_id,
                    "url": d.get("url", ""),
                    "title": d.get("yt_options", {}).get("title", d.get("url", "")),
                    "status": d.get("status", "pending"),
                    "progress": d.get("progress", 0),
                    "speed": d.get("speed", ""),
                    "eta": d.get("eta", ""),
                    "save_path": d.get("save_path", ""),
                    "queue_id": d.get("queue_id", ""),
                    "created_at": d.get("created_at", ""),
                    "completed_at": d.get("completed_at"),
                    "error_message": d.get("error_message", ""),
                    "quality": d.get("yt_options", {}).get("quality", "best"),
                    "format": d.get("yt_options", {}).get("format", "video"),
                    "download_type": "youtube",
                }
            )
        return display_list
