# =============================================================================
# core/enums.py
# =============================================================================
from enum import Enum, auto


class DownloadStatus(Enum):
    """Status of a download."""
    ACTIVE = auto()
    WAITING = auto()
    PAUSED = auto()
    COMPLETE = auto()
    ERROR = auto()
    REMOVED = auto()

    @classmethod
    def from_aria2(cls, status: str) -> "DownloadStatus":
        """Convert aria2 status string to enum."""
        mapping = {
            "active": cls.ACTIVE,
            "waiting": cls.WAITING,
            "paused": cls.PAUSED,
            "complete": cls.COMPLETE,
            "error": cls.ERROR,
            "removed": cls.REMOVED,
        }
        return mapping.get(status, cls.ERROR)
