# ui/icons.py
"""
Icon loading and management for FelfelDM.
Simplified version without SVG dependencies to avoid crashes.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette, QPainterPath
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_icon_cache: dict = {}


def _create_fallback_icon(color: str = "#e67e22", shape: str = "circle") -> QIcon:
    """
    Create a simple colored icon as fallback.
    
    Args:
        color: Hex color string
        shape: "circle", "square", or "download"
    
    Returns:
        QIcon instance
    """
    pixmap = QPixmap(24, 24)
    pixmap.fill(QColor(0, 0, 0, 0))  # transparent
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    if shape == "circle":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 20, 20)
    elif shape == "square":
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, 20, 20, 4, 4)
    elif shape == "download":
        # Draw a simple download arrow in a circle
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 20, 20)
        # Draw white arrow
        painter.setBrush(QColor(255, 255, 255))
        path = QPainterPath()
        path.moveTo(12, 6)
        path.lineTo(6, 12)
        path.lineTo(9, 12)
        path.lineTo(9, 18)
        path.lineTo(15, 18)
        path.lineTo(15, 12)
        path.lineTo(18, 12)
        path.closeSubpath()
        painter.drawPath(path)
    else:
        # Default: circle
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 20, 20)

    painter.end()
    return QIcon(pixmap)


def get_icon(name: str, is_dark: Optional[bool] = None) -> QIcon:
    """
    Get an icon by name with theme-aware coloring.
    
    Args:
        name: Icon name (e.g., "list-add", "document-new", "download")
        is_dark: True for dark theme, False for light theme.
                 If None, auto-detects from application.
    
    Returns:
        QIcon instance
    """
    # Auto-detect theme if not specified
    if is_dark is None:
        app = QApplication.instance()
        if app:
            palette = app.palette()
            bg = palette.color(QPalette.ColorRole.Window)
            brightness = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
            is_dark = brightness < 128
        else:
            is_dark = True

    # Check cache
    cache_key = f"{name}_{is_dark}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # Determine fallback color and shape based on icon name
    fallback_color = "#e67e22"  # default orange
    fallback_shape = "circle"

    # Map icon names to colors and shapes
    icon_map = {
        "list-add": {"color": "#2ecc71", "shape": "circle"},
        "document-new": {"color": "#3498db", "shape": "square"},
        "insert-link": {"color": "#3498db", "shape": "circle"},
        "media-playback-start": {"color": "#2ecc71", "shape": "download"},
        "media-playback-pause": {"color": "#f39c12", "shape": "square"},
        "media-playback-stop": {"color": "#e74c3c", "shape": "square"},
        "preferences-system": {"color": "#9b59b6", "shape": "circle"},
        "folder-open": {"color": "#f39c12", "shape": "square"},
        "edit-delete": {"color": "#e74c3c", "shape": "circle"},
        "torrent": {"color": "#1abc9c", "shape": "circle"},
        "application-exit": {"color": "#e74c3c", "shape": "square"},
        "help-about": {"color": "#3498db", "shape": "circle"},
        "download": {"color": "#e67e22", "shape": "download"},
    }

    # Adjust colors for light theme
    if not is_dark:
        dark_to_light = {
            "#2ecc71": "#27ae60",
            "#3498db": "#2980b9",
            "#f39c12": "#d35400",
            "#e74c3c": "#c0392b",
            "#9b59b6": "#8e44ad",
            "#1abc9c": "#16a085",
            "#e67e22": "#d35400",
        }
        for key, value in dark_to_light.items():
            if key in str(fallback_color):
                fallback_color = value

    # Try system theme first
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        _icon_cache[cache_key] = icon
        return icon

    # Try symbolic versions
    symbolic_names = [
        f"{name}-symbolic",
        f"{name}-symbolic-{'dark' if is_dark else 'light'}",
    ]
    for sym_name in symbolic_names:
        icon = QIcon.fromTheme(sym_name)
        if not icon.isNull():
            _icon_cache[cache_key] = icon
            return icon

    # Use fallback icon with appropriate color and shape
    if name in icon_map:
        info = icon_map[name]
        fallback_color = info["color"]
        fallback_shape = info["shape"]
        # Adjust color for light theme if needed
        if not is_dark:
            light_color_map = {
                "#2ecc71": "#27ae60",
                "#3498db": "#2980b9",
                "#f39c12": "#d35400",
                "#e74c3c": "#c0392b",
                "#9b59b6": "#8e44ad",
                "#1abc9c": "#16a085",
                "#e67e22": "#d35400",
            }
            if fallback_color in light_color_map:
                fallback_color = light_color_map[fallback_color]

    icon = _create_fallback_icon(fallback_color, fallback_shape)
    _icon_cache[cache_key] = icon
    return icon


def clear_icon_cache() -> None:
    """Clear the icon cache (useful when theme changes)."""
    _icon_cache.clear()
    logger.debug("Icon cache cleared")


def get_icon_pixmap(name: str, size: int = 24, is_dark: Optional[bool] = None) -> QPixmap:
    """
    Get an icon as a QPixmap of a specific size.
    
    Args:
        name: Icon name
        size: Desired size in pixels
        is_dark: True for dark theme, False for light theme
    
    Returns:
        QPixmap instance
    """
    icon = get_icon(name, is_dark)
    return icon.pixmap(size, size)
