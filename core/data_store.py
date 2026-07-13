# core/data_store.py

import os
import json
import shutil
from datetime import datetime, time as dtime,timedelta
from pathlib import Path
from appdirs import user_config_dir
import keyring
from core.proxy_manager import ProxyConfig
from typing import Dict, List, Optional, Any

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"


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
    ):
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or os.path.expanduser("~/Downloads")
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads = []
        self.downloads_info = {}
        self.paused = paused
        self.proxy_config = proxy_config
        self.speed_limit = speed_limit

    def to_dict(self):
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
    def from_dict(cls, d):
        name = d.get("name", "Default")
        q = cls(name)
        q.max_concurrent = d.get("max_concurrent", 3)
        q.save_path = d.get("save_path", os.path.expanduser("~/Downloads"))
        q.schedule_enabled = d.get("schedule_enabled", False)
        q.paused = d.get("paused", True)

        st = d.get("schedule_start", "00:00").split(":")
        en = d.get("schedule_end", "23:59").split(":")
        q.schedule_start = dtime(int(st[0]), int(st[1]))
        q.schedule_end = dtime(int(en[0]), int(en[1]))
        q.days = d.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(d.get("downloads", []))
        q.downloads_info = d.get("downloads_info", {})
        q.speed_limit = d.get("speed_limit", 0)

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

    def is_scheduled_now(self):
        """Check if current time is within the scheduled window for this queue"""
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
        """Get the next scheduled time for this queue"""
        if not self.schedule_enabled:
            return None
        
        now = datetime.now()
        today_weekday = now.weekday()
        current_time = now.time().replace(second=0, microsecond=0)
        
        # Check if today is in days
        if today_weekday in self.days:
            start = self.schedule_start
            end = self.schedule_end
            
            if start <= end:
                if current_time <= end:
                    # Today, at start time
                    return datetime.combine(now.date(), start)
            else:
                # Overnight schedule
                if current_time >= start or current_time <= end:
                    return datetime.combine(now.date(), start)
        
        # Find next day
        for i in range(1, 8):
            next_day = (today_weekday + i) % 7
            if next_day in self.days:
                next_date = now.date() + timedelta(days=i)
                return datetime.combine(next_date, self.schedule_start)
        
        return None


class DataStore:
    def __init__(self):
        self.config_dir = Path(user_config_dir("felfelDM"))
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.data_file = self.config_dir / "data.json"

        self.backup_dir = self.config_dir / "backups"
        self.backup_dir.mkdir(exist_ok=True)

        self.queues = []
        self.settings = self._get_default_settings()
        self.download_proxies = {}
        
        self.youtube_downloads_file = self.config_dir / "youtube_downloads.json"
        self.youtube_downloads: Dict[str, dict] = {}  # download_id -> download_data

        self.load()

    def _get_default_settings(self):
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

            self.queues = [Queue.from_dict(q) for q in data.get("queues", [])]
            self.settings.update(data.get("settings", {}))
            self.download_proxies = data.get("download_proxies", {})

            for key, value in self._get_default_settings().items():
                if key not in self.settings:
                    self.settings[key] = value

        except json.JSONDecodeError as e:
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

        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
            if secret:
                self.settings["aria2_secret"] = secret
        except:
            pass

        if not self.queues:
            self.queues = [Queue("Default", paused=True)]

        self._load_youtube_downloads()

    def _load_youtube_downloads(self):
        """بارگذاری دانلودهای یوتیوب از فایل جداگانه"""
        if not self.youtube_downloads_file.exists():
            print("📁 No YouTube downloads file found")
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
        """ذخیره دانلودهای یوتیوب در فایل جداگانه"""
        try:
            temp_file = self.youtube_downloads_file.with_suffix(".tmp")
            
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {"downloads": self.youtube_downloads},
                    f,
                    indent=2,
                    ensure_ascii=False
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
            try:
                keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
            except:
                pass

        try:
            temp_file = self.data_file.with_suffix(".json.tmp")

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "queues": [q.to_dict() for q in self.queues],
                        "settings": self.settings,
                        "download_proxies": (
                            self.download_proxies
                            if hasattr(self, "download_proxies")
                            else {}
                        ),
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
                            "download_proxies": (
                                self.download_proxies
                                if hasattr(self, "download_proxies")
                                else {}
                            ),
                        },
                        f,
                        indent=2,
                        ensure_ascii=False,
                    )
            except:
                print("❌ Failed to save data!")

        # Restore secret
        self.settings["aria2_secret"] = secret
        
        self._save_youtube_downloads()

    
    def add_youtube_download(self, download_data: dict) -> str:
        """
        افزودن دانلود یوتیوب جدید
        
        Args:
            download_data: {
                'id': str,
                'url': str,
                'save_path': str,
                'queue_id': Optional[str],
                'yt_options': dict,
                'proxy': Optional[str],
                'status': str,
                'progress': int,
                'speed': str,
                'eta': str,
                'created_at': str,
                'completed_at': Optional[str],
                'error_message': str
            }
        Returns:
            download_id: str
        """
        download_id = download_data.get('id')
        if not download_id:
            import uuid
            download_id = str(uuid.uuid4())
            download_data['id'] = download_id
        
        self.youtube_downloads[download_id] = download_data
        self._save_youtube_downloads()
        return download_id
    
    def get_youtube_download(self, download_id: str) -> Optional[dict]:
        """دریافت یک دانلود یوتیوب با شناسه"""
        return self.youtube_downloads.get(download_id)
    
    def get_all_youtube_downloads(self) -> List[dict]:
        """دریافت همه دانلودهای یوتیوب"""
        return list(self.youtube_downloads.values())
    
    def get_youtube_downloads_by_status(self, status: str) -> List[dict]:
        """دریافت دانلودهای یوتیوب با وضعیت مشخص"""
        return [d for d in self.youtube_downloads.values() if d.get('status') == status]
    
    def get_youtube_downloads_by_queue(self, queue_id: str) -> List[dict]:
        """دریافت دانلودهای یوتیوب در یک صف خاص"""
        return [d for d in self.youtube_downloads.values() if d.get('queue_id') == queue_id]
    
    def update_youtube_download(self, download_id: str, updates: dict) -> bool:
        """
        به‌روزرسانی یک دانلود یوتیوب
        
        Args:
            download_id: شناسه دانلود
            updates: دیکشنری شامل فیلدهایی که باید به‌روز شوند
        Returns:
            bool: موفقیت یا شکست
        """
        if download_id not in self.youtube_downloads:
            return False
        
        self.youtube_downloads[download_id].update(updates)
        self._save_youtube_downloads()
        return True
    
    def update_youtube_status(self, download_id: str, status: str) -> bool:
        """به‌روزرسانی وضعیت دانلود یوتیوب"""
        return self.update_youtube_download(download_id, {'status': status})
    
    def update_youtube_progress(self, download_id: str, progress: int) -> bool:
        """به‌روزرسانی پیشرفت دانلود یوتیوب"""
        return self.update_youtube_download(download_id, {'progress': progress})
    
    def delete_youtube_download(self, download_id: str) -> bool:
        """حذف یک دانلود یوتیوب"""
        if download_id not in self.youtube_downloads:
            return False
        
        del self.youtube_downloads[download_id]
        self._save_youtube_downloads()
        return True
    
    def clear_completed_youtube_downloads(self) -> int:
        """حذف همه دانلودهای یوتیوب که کامل شده‌اند"""
        completed_ids = [
            d_id for d_id, d in self.youtube_downloads.items()
            if d.get('status') in ['completed', 'cancelled']
        ]
        
        for d_id in completed_ids:
            del self.youtube_downloads[d_id]
        
        if completed_ids:
            self._save_youtube_downloads()
        
        return len(completed_ids)
    
    def get_youtube_downloads_count(self) -> int:
        """تعداد کل دانلودهای یوتیوب"""
        return len(self.youtube_downloads)
    
    def get_youtube_downloads_count_by_status(self, status: str) -> int:
        """تعداد دانلودهای یوتیوب با وضعیت مشخص"""
        return len(self.get_youtube_downloads_by_status(status))
    
    def get_youtube_downloads_info_for_display(self) -> List[dict]:
        """
        دریافت اطلاعات دانلودهای یوتیوب برای نمایش در جدول
        هر آیتم شامل فیلدهای مورد نیاز برای نمایش است
        """
        display_list = []
        for d_id, d in self.youtube_downloads.items():
            display_list.append({
                'id': d_id,
                'url': d.get('url', ''),
                'title': d.get('yt_options', {}).get('title', d.get('url', '')),
                'status': d.get('status', 'pending'),
                'progress': d.get('progress', 0),
                'speed': d.get('speed', ''),
                'eta': d.get('eta', ''),
                'save_path': d.get('save_path', ''),
                'queue_id': d.get('queue_id', ''),
                'created_at': d.get('created_at', ''),
                'completed_at': d.get('completed_at'),
                'error_message': d.get('error_message', ''),
                'quality': d.get('yt_options', {}).get('quality', 'best'),
                'format': d.get('yt_options', {}).get('format', 'video'),
                'download_type': 'youtube'
            })
        return display_list
