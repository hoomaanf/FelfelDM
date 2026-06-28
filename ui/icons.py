# ui/icons.py
"""
Embedded icons as SVG data with fallback to theme.
"""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

ICON_DATA = {
    "list-add": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" fill="currentColor"/>
    </svg>""",
    "document-new": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm8 5h5l-5-5v5z" fill="currentColor"/>
    </svg>""",
    "insert-link": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M9.5 14.5a4.5 4.5 0 0 1 0-9h2.5a4.5 4.5 0 0 1 0 9H9.5zM9.5 7.5a3.5 3.5 0 0 0 0 7h2.5a3.5 3.5 0 0 0 0-7H9.5zm5 0a4.5 4.5 0 0 1 0 9H12a4.5 4.5 0 0 1 0-9h2.5zM12 7.5a3.5 3.5 0 0 0 0 7h2.5a3.5 3.5 0 0 0 0-7H12z" fill="currentColor"/>
    </svg>""",
    "media-playback-pause": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" fill="currentColor"/>
    </svg>""",
    "media-playback-start": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M8 5v14l11-7L8 5z" fill="currentColor"/>
    </svg>""",
    "preferences-system": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0-4a1 1 0 1 1 0 2 1 1 0 0 1 0-2zm0-7a1 1 0 0 1 1 1v1.5a1 1 0 0 1-2 0V5a1 1 0 0 1 1-1zm0 13a1 1 0 0 1 1 1v1.5a1 1 0 0 1-2 0V19a1 1 0 0 1 1-1zm6-6h-1.5a1 1 0 0 1 0-2H18a1 1 0 0 1 0 2zM7.5 12a1 1 0 0 1-1 1H5a1 1 0 0 1 0-2h1.5a1 1 0 0 1 1 1zm11.2-4.9a1 1 0 0 1-1.4 0L15.4 5.2a1 1 0 0 1 1.4-1.4l1.8 1.8a1 1 0 0 1 0 1.4zm-9.9 9.9a1 1 0 0 1-1.4 0L5.1 14.7a1 1 0 0 1 1.4-1.4l1.8 1.8a1 1 0 0 1 0 1.4zm9.9 0a1 1 0 0 1 0-1.4l1.8-1.8a1 1 0 0 1 1.4 1.4l-1.8 1.8a1 1 0 0 1-1.4 0zM5.1 6.4a1 1 0 0 1 1.4 0l1.8 1.8a1 1 0 0 1-1.4 1.4L5.1 7.8a1 1 0 0 1 0-1.4z" fill="currentColor"/>
    </svg>""",
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M4 5a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h16a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1h-8l-2-2H4z" fill="currentColor"/>
    </svg>""",
    "torrent": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" stroke-width="2"/>
        <path d="M12 4l-2 6h4l-2 6" stroke="currentColor" stroke-width="2" fill="none"/>
        <circle cx="12" cy="12" r="1.5" fill="currentColor"/>
    </svg>""",
    "download": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
        <path d="M5 20h14v-2H5v2zm7-3l6-6h-4V5h-4v6H6l6 6z" fill="currentColor"/>
    </svg>""",
}


def get_icon(name: str) -> QIcon:
    """Return a QIcon from embedded SVG data or fallback to theme."""
    svg_data = ICON_DATA.get(name)
    if svg_data:
        try:
            renderer = QSvgRenderer(QByteArray(svg_data.encode()))
            if renderer.isValid():
                pixmap = QPixmap(24, 24)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                return QIcon(pixmap)
        except Exception:
            pass

    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon

    return QIcon()
