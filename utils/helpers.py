# =============================================================================
# utils/helpers.py
# =============================================================================
import os
from typing import Union, List, Optional
from pathlib import Path

# Units for size formatting
UNITS = ["B", "KB", "MB", "GB", "TB", "PB", "EB"]

# Category mapping moved to module level (fixes problem 46)
CATEGORY_MAP = {
    "video": ["mp4", "mkv", "avi", "mov", "wmv", "flv", "webm"],
    "audio": ["mp3", "wav", "flac", "aac", "ogg", "wma"],
    "image": ["jpg", "jpeg", "png", "gif", "bmp", "svg", "webp"],
    "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "rtf"],
    "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz"],
    "executable": ["exe", "msi", "deb", "rpm", "dmg", "pkg"],
}


def _format_with_units(value: Union[int, float], units: List[str], suffix: str = "") -> str:
    """Format a numeric value with appropriate unit suffix."""
    if value <= 0:
        return f"0 {units[0]}{suffix}"

    size_float = float(value)
    unit_index = 0
    while size_float >= 1024 and unit_index < len(units) - 1:
        size_float /= 1024
        unit_index += 1

    if unit_index == 0:
        return f"{int(value)} {units[0]}{suffix}"

    if size_float < 10:
        return f"{size_float:.2f} {units[unit_index]}{suffix}"
    elif size_float < 100:
        return f"{size_float:.1f} {units[unit_index]}{suffix}"
    else:
        return f"{int(size_float)} {units[unit_index]}{suffix}"


def format_size(size: int) -> str:
    """Format a size in bytes to a human-readable string."""
    return _format_with_units(size, UNITS)


def format_speed(bytes_per_sec: int) -> str:
    """Format speed in bytes per second to a human-readable string."""
    return _format_with_units(bytes_per_sec, UNITS, "/s")


def is_valid_url(url: str) -> bool:
    """Basic URL validation (supports http, https, magnet)."""
    if not url:
        return False
    url = url.strip()
    if url.startswith(("http://", "https://")):
        parts = url.split("://", 1)
        if len(parts) == 2 and parts[1]:
            return True
    elif url.startswith("magnet:?xt=urn:"):
        return True
    return False


def check_disk_space(path: Union[str, Path], required_bytes: int = 0) -> bool:
    """
    Check if there is enough free space on the given path.
    If required_bytes <= 0, returns True immediately.
    """
    if required_bytes <= 0:
        return True
    try:
        stat = os.statvfs(str(path))
        free = stat.f_frsize * stat.f_bavail
        return free >= required_bytes
    except OSError:
        return False


def get_category(filename: str) -> str:
    """Guess category based on file extension."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    for category, extensions in CATEGORY_MAP.items():
        if ext in extensions:
            return category
    return "other"
