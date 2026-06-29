# core/queue_model.py
"""
Queue model for download management with scheduling support.
"""

import os
from datetime import datetime, time as dtime
from typing import List, Optional

from core.constants import DEFAULT_DOWNLOAD_PATH


class Queue:
    """Download queue model with scheduling support."""

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
        schedule_dates: Optional[List[str]] = None,
        schedule_times: Optional[List[str]] = None,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.save_path = save_path or str(DEFAULT_DOWNLOAD_PATH)
        self.schedule_enabled = schedule_enabled
        self.schedule_start = schedule_start or dtime(0, 0)
        self.schedule_end = schedule_end or dtime(23, 59)
        self.days = days or [0, 1, 2, 3, 4, 5, 6]
        self.downloads: List[str] = []
        self.paused = paused
        # Advanced scheduling: specific dates and times
        self.schedule_dates = schedule_dates or []  # ISO date strings "YYYY-MM-DD"
        self.schedule_times = schedule_times or []  # "HH:MM" strings

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
            "schedule_dates": self.schedule_dates,
            "schedule_times": self.schedule_times,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Queue":
        name = d.get("name", "Default")
        q = cls(name)
        q.max_concurrent = d.get("max_concurrent", 3)
        q.save_path = d.get("save_path", str(DEFAULT_DOWNLOAD_PATH))
        q.schedule_enabled = d.get("schedule_enabled", False)

        st = d.get("schedule_start", "00:00").split(":")
        en = d.get("schedule_end", "23:59").split(":")
        q.schedule_start = dtime(int(st[0]), int(st[1]))
        q.schedule_end = dtime(int(en[0]), int(en[1]))

        q.days = d.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(d.get("downloads", []))
        q.paused = d.get("paused", True)
        q.schedule_dates = d.get("schedule_dates", [])
        q.schedule_times = d.get("schedule_times", [])
        return q

    def is_scheduled_now(self) -> bool:
        """Check if the queue is allowed to run based on schedule."""
        if not self.schedule_enabled:
            return True

        now = datetime.now()

        # Check specific dates (if any)
        if self.schedule_dates:
            today_str = now.strftime("%Y-%m-%d")
            if today_str not in self.schedule_dates:
                return False

        # Check specific times (if any)
        if self.schedule_times:
            current_time = now.strftime("%H:%M")
            if current_time not in self.schedule_times:
                return False

        # Legacy day-of-week check
        if now.weekday() not in self.days:
            return False

        # Legacy time range check
        t = now.time().replace(second=0, microsecond=0)
        start = self.schedule_start
        end = self.schedule_end
        if start <= end:
            return start <= t <= end
        return t >= start or t <= end
