# =============================================================================
# ui/icons.py
# =============================================================================
from typing import Dict, Optional

from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt

# Simple in-memory icon cache
_icon_cache: Dict[str, QIcon] = {}


def get_icon(name: str, fallback_text: str = "", size: int = 24) -> QIcon:
    """
    Get an icon by name, using a cache. If not found, create from text.

    Args:
        name: Icon name (e.g., "folder", "file").
        fallback_text: Text to display if icon not found.
        size: Size for fallback pixmap.

    Returns:
        QIcon instance.
    """
    cache_key = f"{name}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # Try to load from theme or standard pixmap
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        _icon_cache[cache_key] = icon
        return icon

    # Fallback: create a colored square with text
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(200, 200, 200))
    # Optionally draw text
    _icon_cache[cache_key] = QIcon(pixmap)
    return _icon_cache[cache_key]


def clear_icon_cache() -> None:
    """Clear the icon cache to free memory and force reload."""
    global _icon_cache
    _icon_cache.clear()


def set_icon_theme(theme: str) -> None:
    """
    Set the system icon theme and clear cache.

    Args:
        theme: Theme name (e.g., "Papirus", "Adwaita").
    """
    # In PyQt, we can set the theme for QIcon
    from PyQt6.QtGui import QIcon
    QIcon.setThemeName(theme)
    clear_icon_cache()
