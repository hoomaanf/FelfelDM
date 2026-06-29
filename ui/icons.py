# ui/icons.py
"""
Icon loader for FelfelDM.
Loads icons from the Papirus theme directories (icons/Papirus-Dark/ and icons/Papirus-Light/)
with fallback to system theme.
"""

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from utils.style import detect_theme

# Base directory for icons
ICONS_DIR = Path(__file__).parent.parent / "icons"


class IconLoader:
    """
    Loads icons from Papirus theme directories with automatic dark/light selection.
    """

    _instance = None
    _dark_icons: Optional[Path] = None
    _light_icons: Optional[Path] = None
    _cache: dict = {}
    _current_theme: Optional[bool] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_paths()
        return cls._instance

    def _init_paths(self) -> None:
        """Initialize paths to Papirus icon directories."""
        dark_path = ICONS_DIR / "Papirus-Dark"
        light_path = ICONS_DIR / "Papirus-Light"

        if dark_path.exists():
            self._dark_icons = dark_path
        if light_path.exists():
            self._light_icons = light_path

    def clear_cache(self) -> None:
        """Clear the icon cache to force reloading icons."""
        self._cache.clear()
        self._current_theme = None

    def get_icon(self, name: str, size: int = 24) -> QIcon:
        """
        Get an icon by name with the appropriate theme (dark/light).

        Args:
            name: Icon name (e.g., 'list-add', 'document-new')
            size: Icon size in pixels

        Returns:
            QIcon instance
        """
        # Detect current theme
        is_dark = detect_theme()

        # If theme changed, clear cache to reload icons
        if self._current_theme is not None and self._current_theme != is_dark:
            self.clear_cache()

        self._current_theme = is_dark

        cache_key = f"{name}_{size}_{is_dark}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        icons_path = self._dark_icons if is_dark else self._light_icons

        icon = QIcon()

        if icons_path:
            for ext in [".svg", ".png"]:
                icon_file = icons_path / f"{name}{ext}"
                if icon_file.exists():
                    icon.addFile(str(icon_file), Qt.Size(size, size))
                    break

        if icon.isNull():
            fallback_icon = QIcon.fromTheme(name)
            if not fallback_icon.isNull():
                icon = fallback_icon

        self._cache[cache_key] = icon
        return icon


# Singleton instance
_loader = IconLoader()


def get_icon(name: str, size: int = 24) -> QIcon:
    """
    Get an icon by name with automatic dark/light theme detection.

    Args:
        name: Icon name (e.g., 'list-add', 'document-new', 'download')
        size: Icon size in pixels (default: 24)

    Returns:
        QIcon instance
    """
    return _loader.get_icon(name, size)


def get_icon_path(name: str) -> Optional[Path]:
    """
    Get the file path of an icon if it exists in the Papirus theme.

    Args:
        name: Icon name

    Returns:
        Path to the icon file, or None if not found
    """
    is_dark = detect_theme()
    icons_path = _loader._dark_icons if is_dark else _loader._light_icons

    if icons_path:
        for ext in [".svg", ".png"]:
            icon_file = icons_path / f"{name}{ext}"
            if icon_file.exists():
                return icon_file
    return None


def clear_icon_cache() -> None:
    """Clear the icon cache globally."""
    _loader.clear_cache()
