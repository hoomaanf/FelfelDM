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
        days: Optional[List[int]] = None,
        schedule_start: Optional[str] = None,
        schedule_end: Optional[str] = None,
        enabled: bool = True,
        queue_id: Optional[str] = None,
    ) -> None:
        self.id: str = queue_id or str(uuid.uuid4())
        self.name: str = name
        self.urls: List[str] = urls or []
        self.download_dir: str = download_dir
        self.schedule_dates: List[str] = schedule_dates or []
        self.schedule_times: List[str] = schedule_times or []
        self.days: List[int] = days or []
        self.schedule_start: Optional[str] = schedule_start
        self.schedule_end: Optional[str] = schedule_end
        self.enabled: bool = enabled
        self.timezone = pytz.timezone("Asia/Tehran")

    def is_scheduled_now(self) -> bool:
        """Determine if the queue should run now based on priority logic."""
        if not self.enabled:
            return False

        now = datetime.now(self.timezone)
        current_date = now.date()
        current_time = now.time()

        if self.schedule_dates:
            date_str = current_date.isoformat()
            return date_str in self.schedule_dates

        if self.schedule_times:
            time_str = current_time.strftime("%H:%M")
            return time_str in self.schedule_times

        if self.days:
            current_day = now.isoweekday() - 1
            if current_day not in self.days:
                return False

        if self.schedule_start and self.schedule_end:
            start = datetime.strptime(self.schedule_start, "%H:%M").time()
            end = datetime.strptime(self.schedule_end, "%H:%M").time()
            return start <= current_time <= end
        elif self.schedule_start:
            start = datetime.strptime(self.schedule_start, "%H:%M").time()
            return current_time >= start
        elif self.schedule_end:
            end = datetime.strptime(self.schedule_end, "%H:%M").time()
            return current_time <= end

        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert queue to dictionary for serialization."""
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
        """Create a Queue instance from a dictionary."""
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
    ) -> None:
        self.download_dir: str = download_dir
        self.speed_limit: int = speed_limit
        self.max_concurrent: int = max_concurrent
        self.aria2_secret: str = aria2_secret

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            "download_dir": self.download_dir,
            "speed_limit": self.speed_limit,
            "max_concurrent": self.max_concurrent,
            "aria2_secret": self.aria2_secret,
        }
