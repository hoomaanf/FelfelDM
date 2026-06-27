# core/data_store.py

import os
import json
from datetime import datetime, time as dtime
from appdirs import user_config_dir
import keyring

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"

class Queue:
    def __init__(self, name, max_concurrent=3, save_path="", schedule_enabled=False,
                 schedule_start=None, schedule_end=None, days=None, paused=True):
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or os.path.expanduser("~/Downloads")
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads = []
        self.paused = paused

    def to_dict(self):
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
    def from_dict(cls, d):
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

    def is_scheduled_now(self):
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


class DataStore:
    PATH = os.path.join(user_config_dir("felfelDM"), "data.json")

    def __init__(self):
        os.makedirs(os.path.dirname(self.PATH), exist_ok=True)
        self.queues = []
       
        self.settings = {
            "aria2_host": "http://localhost",
            "aria2_port": 6800,
            "aria2_secret": "",
            "connections": 8,
            "max_tries": 0,
            "max_concurrent": 5,
            "shutdown_after_finish": False,
            "speed_limit": 0,
            "auto_clear_completed": False
        }
        self.load()
        if not self.queues:
            self.queues = [Queue("Default", paused=True)]
    
    def load(self):
        try:
            with open(self.PATH) as f:
                data = json.load(f)
            self.queues = [Queue.from_dict(q) for q in data.get("queues", [])]
            self.settings.update(data.get("settings", {}))
            
            for q in self.queues:
                if not hasattr(q, 'paused'):
                    q.paused = True
                if not hasattr(q, 'schedule_enabled'):
                    q.schedule_enabled = False
                if not hasattr(q, 'schedule_start'):
                    q.schedule_start = dtime(0, 0)
                if not hasattr(q, 'schedule_end'):
                    q.schedule_end = dtime(23, 59)
                if not hasattr(q, 'days'):
                    q.days = [0, 1, 2, 3, 4, 5, 6]
                    
        except Exception as e:
            print(f"⚠ Error loading data: {e}")
            pass
        secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
        if secret is not None:
            self.settings["aria2_secret"] = secret
    def save(self):
        secret = self.settings.pop("aria2_secret", "")
        keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
        
        with open(self.PATH, "w") as f:
            json.dump({
                "queues": [q.to_dict() for q in self.queues],
                "settings": self.settings,
            }, f, indent=2)
        
        self.settings["aria2_secret"] = secret