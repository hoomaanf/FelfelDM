# =============================================================================
# core/queue_model.py
# =============================================================================
import uuid
from datetime import datetime, time, timedelta
from typing import Optional, List, Dict, Any
import pytz


class Queue:
    """Queue model for scheduled downloads with proper timezone-aware scheduling."""

    def __init__(
        self,
        name: str = "",
        urls: Optional[List[str]] = None,
        download_dir: str = "",
        schedule_dates: Optional[List[str]] = None,
        schedule_times: Optional[List[str]] = None,
        days: Optional[List[int]] = None,  # 0=Monday, 6=Sunday
        schedule_start: Optional[str] = None,
        schedule_end: Optional[str] = None,
        enabled: bool = True,
        queue_id: Optional[str] = None,
    ):
        self.id = queue_id or str(uuid.uuid4())
        self.name = name
        self.urls = urls or []
        self.download_dir = download_dir
        # schedule_dates: list of "YYYY-MM-DD"
        self.schedule_dates = schedule_dates or []
        # schedule_times: list of "HH:MM"
        self.schedule_times = schedule_times or []
        # days: list of int, 0=Monday, 6=Sunday
        self.days = days or []
        self.schedule_start = schedule_start  # "HH:MM"
        self.schedule_end = schedule_end  # "HH:MM"
        self.enabled = enabled
        self.timezone = pytz.timezone("Asia/Tehran")  # or system default

    def is_scheduled_now(self) -> bool:
        """
        Determine if the queue should run now.
        Logic priority:
        1. If schedule_dates exists, only check dates.
        2. Else if schedule_times exists, only check times.
        3. Else use days + schedule_start/end.
        """
        if not self.enabled:
            return False

        now = datetime.now(self.timezone)
        current_date = now.date()
        current_time = now.time()

        # Priority 1: schedule_dates
        if self.schedule_dates:
            date_str = current_date.isoformat()
            if date_str in self.schedule_dates:
                return True
            return False

        # Priority 2: schedule_times
        if self.schedule_times:
            time_str = current_time.strftime("%H:%M")
            if time_str in self.schedule_times:
                return True
            return False

        # Priority 3: days + schedule_start/end
        if self.days:
            # 0=Monday, 6=Sunday in our model, but datetime.isoweekday() returns 1=Monday, 7=Sunday
            current_day = now.isoweekday() - 1  # convert to 0-6
            if current_day not in self.days:
                return False

        # Check time range (if specified)
        if self.schedule_start and self.schedule_end:
            start = datetime.strptime(self.schedule_start, "%H:%M").time()
            end = datetime.strptime(self.schedule_end, "%H:%M").time()
            if start <= current_time <= end:
                return True
            return False
        elif self.schedule_start:
            start = datetime.strptime(self.schedule_start, "%H:%M").time()
            if current_time >= start:
                return True
            return False
        elif self.schedule_end:
            end = datetime.strptime(self.schedule_end, "%H:%M").time()
            if current_time <= end:
                return True
            return False

        # No scheduling restrictions: always active
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "urls": self.urls,
            "download_dir": self.download_dir,
            "schedule_dates": self.schedule_dates,
            "schedule_times": self.schedule_times,
            "days": self.days,
            "schedule_start": self.schedule_start,
            "schedule_end": self.schedule_end,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Queue":
        return cls(
            queue_id=data.get("id"),
            name=data.get("name", ""),
            urls=data.get("urls", []),
            download_dir=data.get("download_dir", ""),
            schedule_dates=data.get("schedule_dates", []),
            schedule_times=data.get("schedule_times", []),
            days=data.get("days", []),
            schedule_start=data.get("schedule_start"),
            schedule_end=data.get("schedule_end"),
            enabled=data.get("enabled", True),
        )


class Settings:
    """Application settings."""

    def __init__(
        self,
        download_dir: str = "",
        speed_limit: int = 0,
        max_concurrent: int = 5,
        aria2_secret: str = "",
    ):
        self.download_dir = download_dir
        self.speed_limit = speed_limit
        self.max_concurrent = max_concurrent
        self.aria2_secret = aria2_secret

    def to_dict(self) -> Dict[str, Any]:
        return {
            "download_dir": self.download_dir,
            "speed_limit": self.speed_limit,
            "max_concurrent": self.max_concurrent,
            "aria2_secret": self.aria2_secret,
        }
