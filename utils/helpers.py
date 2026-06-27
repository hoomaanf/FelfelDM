# Requires: PyQt6>=6.4.0

"""
Helper functions for formatting, disk space, etc.
"""

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
    if size < 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def format_speed(speed: int) -> str:
    if speed == 0:
        return "0 B/s"
    for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
        if speed < 1024.0:
            return f"{speed:.1f} {unit}"
        speed /= 1024.0
    return f"{speed:.1f} TB/s"


def ensure_dir(path: Union[str, Path]) -> bool:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def check_disk_space(path: str, required_bytes: int = 0) -> bool:
    """Check if there is enough free space on the device containing path."""
    try:
        stat = shutil.disk_usage(path)
        if required_bytes == 0:
            return True
        return stat.free >= required_bytes
    except Exception:
        return True
