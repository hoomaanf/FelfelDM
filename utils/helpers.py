# utils/helpers.py
"""
Helper functions for formatting, disk space, etc.
"""

import math
import os
import shutil
from pathlib import Path
from typing import Union

from PyQt6.QtGui import QIcon


def get_icon(name: str) -> QIcon:
    """Fallback icon from theme."""
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon
    return QIcon()


def format_size(size: int) -> str:
    """
    Format a size in bytes to a human-readable string.
    Uses math.log for efficiency.
    """
    if size < 0:
        return "0 B"
    if size == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]
    # Use math.log to determine the appropriate unit
    if size < 1024:
        return f"{size:.1f} B"

    exponent = min(int(math.log(size, 1024)), len(units) - 1)
    value = size / (1024 ** exponent)
    # Show one decimal place for values < 100, otherwise no decimals
    if value < 100:
        return f"{value:.1f} {units[exponent]}"
    else:
        return f"{value:.0f} {units[exponent]}"


def format_speed(speed: int) -> str:
    """
    Format a speed in bytes per second to a human-readable string.
    """
    if speed == 0:
        return "0 B/s"
    units = ["B/s", "KB/s", "MB/s", "GB/s", "TB/s"]
    if speed < 1024:
        return f"{speed:.1f} {units[0]}"
    exponent = min(int(math.log(speed, 1024)), len(units) - 1)
    value = speed / (1024 ** exponent)
    if value < 100:
        return f"{value:.1f} {units[exponent]}"
    else:
        return f"{value:.0f} {units[exponent]}"


def ensure_dir(path: Union[str, Path]) -> bool:
    """Ensure a directory exists."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def check_disk_space(path: str, required_bytes: int = 0) -> bool:
    """
    Check if there is enough free space on the device containing path.
    """
    try:
        stat = shutil.disk_usage(path)
        if required_bytes == 0:
            return True
        return stat.free >= required_bytes
    except Exception:
        return True


def get_category(filename: str) -> str:
    """
    Get the category of a file based on its extension.
    """
    ext = os.path.splitext(filename)[1].lower()
    categories = {
        ".mp4": "Video",
        ".mkv": "Video",
        ".avi": "Video",
        ".mov": "Video",
        ".wmv": "Video",
        ".flv": "Video",
        ".webm": "Video",
        ".mp3": "Audio",
        ".wav": "Audio",
        ".flac": "Audio",
        ".aac": "Audio",
        ".ogg": "Audio",
        ".m4a": "Audio",
        ".zip": "Archive",
        ".rar": "Archive",
        ".7z": "Archive",
        ".tar": "Archive",
        ".gz": "Archive",
        ".bz2": "Archive",
        ".xz": "Archive",
        ".iso": "Disk Image",
        ".img": "Disk Image",
        ".pdf": "Document",
        ".doc": "Document",
        ".docx": "Document",
        ".xls": "Document",
        ".xlsx": "Document",
        ".ppt": "Document",
        ".pptx": "Document",
        ".txt": "Document",
        ".md": "Document",
        ".epub": "Document",
        ".exe": "Executable",
        ".msi": "Executable",
        ".deb": "Executable",
        ".rpm": "Executable",
        ".apk": "Executable",
        ".dmg": "Executable",
        ".torrent": "Torrent",
        ".magnet": "Torrent",
    }
    return categories.get(ext, "Other")
