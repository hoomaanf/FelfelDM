# ui/icons.py
"""
Embedded icons as SVG data with fallback to theme.
"""

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QSize

# SVG icons for common actions
ICON_DATA = {
    "list-add": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M14 7H9V2H7v5H2v2h5v5h2V9h5z" fill="currentColor"/>
    </svg>""",
    "document-new": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M3 1h8l4 4v9a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1zm7 4h4l-4-4v4z" fill="currentColor"/>
    </svg>""",
    "insert-link": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M6.5 3.5a3.5 3.5 0 0 1 0 7H4a3.5 3.5 0 0 1 0-7h2.5zM4 2.5a4.5 4.5 0 0 0 0 9h2.5a4.5 4.5 0 0 0 0-9H4zm7.5 0a4.5 4.5 0 0 0 0 9H9a4.5 4.5 0 0 0 0-9h2.5zM9 2.5a3.5 3.5 0 0 1 0 7h-2.5a3.5 3.5 0 0 1 0-7H9z" fill="currentColor"/>
    </svg>""",
    "media-playback-pause": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M5 2a1 1 0 0 1 1 1v10a1 1 0 0 1-2 0V3a1 1 0 0 1 1-1zm6 0a1 1 0 0 1 1 1v10a1 1 0 0 1-2 0V3a1 1 0 0 1 1-1z" fill="currentColor"/>
    </svg>""",
    "media-playback-start": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M4.5 2.5a1 1 0 0 1 1.5-.9l8 5.5a1 1 0 0 1 0 1.8l-8 5.5a1 1 0 0 1-1.5-.9V2.5z" fill="currentColor"/>
    </svg>""",
    "preferences-system": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 12.5A5.5 5.5 0 1 1 8 2.5a5.5 5.5 0 0 1 0 11zM7 4h2v5H7V4zm0 6h2v2H7v-2z" fill="currentColor"/>
    </svg>""",
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M1.5 3A1.5 1.5 0 0 0 0 4.5v7A1.5 1.5 0 0 0 1.5 13h12a1.5 1.5 0 0 0 1.5-1.5v-7A1.5 1.5 0 0 0 13.5 3H8.5L7 1.5H1.5z" fill="currentColor"/>
    </svg>""",
    "torrent": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.5A6.5 6.5 0 1 1 8 1.5a6.5 6.5 0 0 1 0 13zM7 4h2v5H7V4zm0 6h2v2H7v-2z" fill="currentColor"/>
    </svg>""",
    "download": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M8 1a1 1 0 0 1 1 1v6h3.5a.5.5 0 0 1 .354.854l-4.5 4.5a.5.5 0 0 1-.708 0l-4.5-4.5A.5.5 0 0 1 3.5 8H7V2a1 1 0 0 1 1-1z" fill="currentColor"/>
        <path d="M1 14a1 1 0 0 1 1-1h12a1 1 0 0 1 0 2H2a1 1 0 0 1-1-1z" fill="currentColor"/>
    </svg>""",
}


def get_icon(name: str) -> QIcon:
    """
    Return a QIcon from embedded SVG data or fallback to theme.
    """
    # Try embedded SVG first
    svg_data = ICON_DATA.get(name)
    if svg_data:
        from PyQt6.QtCore import QByteArray
        from PyQt6.QtGui import QIcon, QPixmap
        from PyQt6.QtSvg import QSvgRenderer

        renderer = QSvgRenderer(QByteArray(svg_data.encode()))
        if renderer.isValid():
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)

    # Fallback to theme
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon

    # Final fallback: empty icon
    return QIcon()
