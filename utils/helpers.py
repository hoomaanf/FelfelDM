# Requires: PyQt6>=6.4.0
"""Helper functions for formatting, disk space, etc."""

import shutil
from pathlib import Path
from typing import Union

from PyQt6.QtGui import QIcon


def get_icon(name: str) -> QIcon:
    icon = QIcon.fromTheme(name)
    return icon if not icon.isNull() else QIcon()


def _format_size_generic(size: float, unit: str, divisor: float = 1024.0) -> str:
    units = ['B', 'KB', 'MB', 'GB', 'TB'] if unit == 'B' else ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s']
    unit_index = 0
    if size < 0:
        return f"0 {unit}"
    while size >= divisor and unit_index < len(units) - 1:
        size /= divisor
        unit_index += 1
    return f"{size:.1f} {units[unit_index]}" if unit_index < len(units) else f"{size:.1f} {units[-1]}"


def format_size(size: int) -> str:
    return "0 B" if size < 0 else _format_size_generic(float(size), "B")


def format_speed(speed: int) -> str:
    if speed <= 0:
        return "0 B/s"
    return _format_size_generic(float(speed), "B/s")


def ensure_dir(path: Union[str, Path]) -> bool:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def check_disk_space(path: str, required_bytes: int = 0) -> bool:
    try:
        stat = shutil.disk_usage(path)
        return stat.free >= required_bytes if required_bytes > 0 else True
    except Exception:
        return True
