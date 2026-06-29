# ui/icons.py
"""
Icon loading and management for FelfelDM.
Supports both system theme icons and embedded SVG fallbacks.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QByteArray
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPalette  # ← QPalette اضافه شد
from PyQt6.QtWidgets import QApplication
from PyQt6.QtSvg import QSvgRenderer

logger = logging.getLogger(__name__)


# =============================================================================
# Embedded SVG Icons (simple, clean design)
# =============================================================================

ICON_DATA = {
    "list-add": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>""",
    "document-new": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>""",
    "insert-link": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>""",
    "media-playback-start": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>""",
    "media-playback-pause": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>""",
    "preferences-system": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 1v2"/><path d="M12 21v2"/><path d="M4.22 4.22l1.42 1.42"/><path d="M18.36 18.36l1.42 1.42"/><path d="M1 12h2"/><path d="M21 12h2"/><path d="M4.22 19.78l1.42-1.42"/><path d="M18.36 5.64l1.42-1.42"/></svg>""",
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/><path d="M4 12h16"/></svg>""",
    "edit-delete": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></svg>""",
    "torrent": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="M8 12h8"/></svg>""",
    "application-exit": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>""",
    "help-about": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>""",
    "media-playback-stop": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16"/></svg>""",
    "download": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>""",
}


# =============================================================================
# Icon Cache
# =============================================================================

_icon_cache: dict = {}


def _render_svg(svg_data: str, is_dark: bool) -> QIcon:
    """
    Render an SVG string to a QIcon with the appropriate color.
    
    Args:
        svg_data: SVG string
        is_dark: True for dark theme, False for light theme
    
    Returns:
        QIcon instance
    """
    color = "#e0e0e0" if is_dark else "#222222"
    svg_colored = svg_data.replace("currentColor", color)
    
    renderer = QSvgRenderer(QByteArray(svg_colored.encode()))
    if not renderer.isValid():
        return QIcon()
    
    pixmap = QPixmap(24, 24)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    
    return QIcon(pixmap)


def get_icon(name: str, is_dark: Optional[bool] = None) -> QIcon:
    """Get an icon by name with theme-aware coloring."""
    if is_dark is None:
        app = QApplication.instance()
        if app:
            palette = app.palette()
            bg = palette.color(QPalette.ColorRole.Window)  # ← حالا QPalette تعریف شده
            brightness = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
            is_dark = brightness < 128
        else:
            is_dark = True
    
    cache_key = f"{name}_{is_dark}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        _icon_cache[cache_key] = icon
        return icon
    
    fallback_names = [f"{name}-symbolic", f"{name}-symbolic-{'dark' if is_dark else 'light'}"]
    for fallback in fallback_names:
        icon = QIcon.fromTheme(fallback)
        if not icon.isNull():
            _icon_cache[cache_key] = icon
            return icon
    
    if name in ICON_DATA:
        icon = _render_svg(ICON_DATA[name], is_dark)
        if not icon.isNull():
            _icon_cache[cache_key] = icon
            return icon
    
    logger.warning("Icon not found: %s", name)
    _icon_cache[cache_key] = QIcon()
    return _icon_cache[cache_key]


def clear_icon_cache() -> None:
    _icon_cache.clear()
    logger.debug("Icon cache cleared")


def get_icon_pixmap(name: str, size: int = 24, is_dark: Optional[bool] = None) -> QPixmap:
    icon = get_icon(name, is_dark)
    return icon.pixmap(size, size)
