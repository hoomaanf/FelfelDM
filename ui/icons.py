# =============================================================================
# ui/icons.py
# =============================================================================
from typing import Dict, Optional

from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtCore import Qt

# Try to import SVG support
try:
    from PyQt6.QtSvg import QSvgRenderer
    HAS_SVG = True
except ImportError:
    HAS_SVG = False

_icon_cache: Dict[str, QIcon] = {}


def get_icon(name: str, fallback_text: str = "", size: int = 24) -> QIcon:
    """
    Get an icon by name, using a cache. If not found, try SVG, system theme, or fallback.
    """
    cache_key = f"{name}_{size}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # Try to load from system theme
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        _icon_cache[cache_key] = icon
        return icon

    # Try to load SVG if available (simplified, not implemented)
    # In a real implementation, you might load from a resource.
    # For now, create a fallback pixmap.
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(200, 200, 200))
    _icon_cache[cache_key] = QIcon(pixmap)
    return _icon_cache[cache_key]


def clear_icon_cache() -> None:
    """Clear the icon cache."""
    global _icon_cache
    _icon_cache.clear()


def set_icon_theme(theme: str) -> None:
    """Set the system icon theme and clear cache."""
    from PyQt6.QtGui import QIcon
    QIcon.setThemeName(theme)
    clear_icon_cache()
