# core/enums.py
"""
Enumerations for download states and other constants.
"""

from enum import Enum, auto
from typing import Optional


class DownloadStatus(Enum):
    """Download status enumeration."""

    ACTIVE = "Active"
    WAITING = "Waiting"
    PAUSED = "Paused"
    COMPLETE = "Complete"
    ERROR = "Error"
    REMOVED = "Removed"
    UNKNOWN = "Unknown"

    @classmethod
    def from_string(cls, value: str) -> "DownloadStatus":
        """
        Convert a string status to an enum member.

        Args:
            value: String status (e.g., 'active', 'paused')

        Returns:
            DownloadStatus enum member
        """
        mapping = {
            "active": cls.ACTIVE,
            "waiting": cls.WAITING,
            "paused": cls.PAUSED,
            "complete": cls.COMPLETE,
            "error": cls.ERROR,
            "removed": cls.REMOVED,
        }
        return mapping.get(value.lower(), cls.UNKNOWN)

    def __str__(self) -> str:
        return self.value


class QueueSchedule(Enum):
    """Queue schedule status."""
    RUNNING = auto()
    PAUSED = auto()
    SCHEDULED = auto()


class ConnectionState(Enum):
    """Connection state enumeration."""
    CONNECTED = auto()
    DISCONNECTED = auto()
    CONNECTING = auto()
    ERROR = auto()
