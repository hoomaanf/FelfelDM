# core/queue_model.py
"""
Queue model for download management.
"""

import os
from datetime import datetime, time as dtime
from typing import List, Optional


class Queue:
    """Download queue model - single source of truth."""

    def __init__(
        self,
        name: str,
        max_concurrent: int = 3,
        save_path: str = "",
        schedule_enabled: bool = False,
        schedule_start=None,
        schedule_end=None,
        days=None,
        paused: bool = True,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or os.path.expanduser("~/Downloads")
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads: List[str] = []  # List of GIDs
        self.paused = paused

    def to_dict(self) -> dict:
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
    def from_dict(cls, d: dict) -> "Queue":
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

    def is_scheduled_now(self) -> bool:
        """Check if the queue is allowed to run based on schedule."""
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
        return t >= start or t <= end
