from datetime import datetime, time as dtime
import os


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
        speed_limit=0,
        proxy_config=None,
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
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "save_path": self.save_path,
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": self.schedule_start.strftime("%H:%M"),
            "schedule_end": self.schedule_end.strftime("%H:%M"),
            "days": self.days,
            "downloads": self.downloads,
            "downloads_info": self.downloads_info,
            "paused": self.paused,
            "speed_limit": self.speed_limit,
        }

    @classmethod
    def from_dict(cls, data):
        name = data.get("name", "Default")
        q = cls(
            name=name,
            max_concurrent=data.get("max_concurrent", 3),
            save_path=data.get("save_path", os.path.expanduser("~/Downloads")),
            schedule_enabled=data.get("schedule_enabled", False),
            paused=data.get("paused", True),
            speed_limit=data.get("speed_limit", 0),
        )

        st = data.get("schedule_start", "00:00").split(":")
        en = data.get("schedule_end", "23:59").split(":")
        q.schedule_start = dtime(int(st[0]), int(st[1]))
        q.schedule_end = dtime(int(en[0]), int(en[1]))
        q.days = data.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(data.get("downloads", []))
        q.downloads_info = data.get("downloads_info", {})
        q.proxy_config = data.get("proxy_config", None)
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
