# ui/icons.py
"""
Embedded icons as SVG data with fallback to theme.
"""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

# Simple SVG icons for common actions
# These are minimal but valid SVGs that provide visual feedback
ICON_DATA = {
    "list-add": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <rect x="2" y="2" width="12" height="12" rx="2" fill="#4a6a9a" stroke="white" stroke-width="1"/>
        <line x1="5" y1="8" x2="11" y2="8" stroke="white" stroke-width="2"/>
        <line x1="8" y1="5" x2="8" y2="11" stroke="white" stroke-width="2"/>
    </svg>""",
    "document-new": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <rect x="2" y="2" width="12" height="12" rx="1" fill="#4a6a9a" stroke="white" stroke-width="1"/>
        <line x1="5" y1="5" x2="11" y2="5" stroke="white" stroke-width="1.5"/>
        <line x1="5" y1="8" x2="11" y2="8" stroke="white" stroke-width="1.5"/>
        <line x1="5" y1="11" x2="9" y2="11" stroke="white" stroke-width="1.5"/>
    </svg>""",
    "insert-link": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <circle cx="5" cy="8" r="3" fill="none" stroke="#4a6a9a" stroke-width="2"/>
        <circle cx="11" cy="8" r="3" fill="none" stroke="#4a6a9a" stroke-width="2"/>
        <line x1="7" y1="6" x2="9" y2="6" stroke="#4a6a9a" stroke-width="2"/>
        <line x1="7" y1="10" x2="9" y2="10" stroke="#4a6a9a" stroke-width="2"/>
    </svg>""",
    "media-playback-pause": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <rect x="2" y="3" width="12" height="10" rx="2" fill="#f1c40f"/>
        <rect x="5" y="5" width="2" height="6" fill="white"/>
        <rect x="9" y="5" width="2" height="6" fill="white"/>
    </svg>""",
    "media-playback-start": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <rect x="2" y="3" width="12" height="10" rx="2" fill="#2ecc71"/>
        <polygon points="6,5 6,11 11,8" fill="white"/>
    </svg>""",
    "preferences-system": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <circle cx="8" cy="8" r="6" fill="none" stroke="#4a6a9a" stroke-width="2"/>
        <circle cx="8" cy="8" r="2" fill="#4a6a9a"/>
        <line x1="8" y1="1" x2="8" y2="3" stroke="#4a6a9a" stroke-width="2"/>
        <line x1="8" y1="13" x2="8" y2="15" stroke="#4a6a9a" stroke-width="2"/>
        <line x1="1" y1="8" x2="3" y2="8" stroke="#4a6a9a" stroke-width="2"/>
        <line x1="13" y1="8" x2="15" y2="8" stroke="#4a6a9a" stroke-width="2"/>
    </svg>""",
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <path d="M2 3a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V5a1 1 0 0 0-1-1H8L6 3H2z" fill="#f39c12" stroke="#e67e22" stroke-width="1"/>
        <rect x="1" y="5" width="14" height="6" rx="1" fill="#f1c40f" stroke="#e67e22" stroke-width="0.5"/>
    </svg>""",
    "torrent": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <circle cx="8" cy="8" r="7" fill="none" stroke="#e74c3c" stroke-width="2"/>
        <path d="M5 5l6 6M11 5l-6 6" stroke="#e74c3c" stroke-width="2"/>
        <circle cx="8" cy="8" r="1.5" fill="#e74c3c"/>
    </svg>""",
    "download": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">
        <rect x="2" y="2" width="12" height="12" rx="2" fill="#3498db" stroke="white" stroke-width="1"/>
        <polygon points="8,4 8,10 5,7 11,7" fill="white"/>
        <line x1="4" y1="12" x2="12" y2="12" stroke="white" stroke-width="2"/>
    </svg>""",
}


def get_icon(name: str) -> QIcon:
    """
    Return a QIcon from embedded SVG data or fallback to theme.
    """
    # Try embedded SVG first
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
            # Fall through to theme fallback
            pass

    # Fallback to theme
    icon = QIcon.fromTheme(name)
    if not icon.isNull():
        return icon

    # Final fallback: empty icon
    return QIcon()
