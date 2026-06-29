# =============================================================================
# utils/style.py
# =============================================================================
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont
from PyQt6.QtCore import Qt

logger = logging.getLogger(__name__)


def setup_font(app: QApplication) -> None:
    """Set up application font, preferring Vazir or IRANSansWeb if available."""
    available_fonts = QFontDatabase.families()

    preferred_fonts = ["Vazir", "IRANSansWeb", "IRANSans", "Tahoma", "Arial"]
    font_name = "Arial"  # fallback

    for name in preferred_fonts:
        if name in available_fonts:
            font_name = name
            break

    font = QFont(font_name, 10)
    app.setFont(font)
    logger.info(f"Font set to: {font_name}")


def setup_style(app: QApplication) -> None:
    """Apply global stylesheet and color scheme."""
    style = """
    QMainWindow {
        background-color: #2b2b2b;
    }
    QWidget {
        background-color: #2b2b2b;
        color: #ffffff;
        font-size: 10pt;
    }
    QTableWidget, QTableView {
        background-color: #3c3c3c;
        alternate-background-color: #4a4a4a;
        gridline-color: #555;
    }
    QHeaderView::section {
        background-color: #3c3c3c;
        padding: 4px;
        border: 1px solid #555;
    }
    QPushButton {
        background-color: #4a4a5a;
        border: 1px solid #6a6a7a;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background-color: #5a5a6a;
    }
    QLineEdit, QTextEdit {
        background-color: #3c3c3c;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 4px;
    }
    QProgressBar {
        border: 1px solid #555;
        border-radius: 4px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #4a8bc2;
        border-radius: 4px;
    }
    """
    app.setStyleSheet(style)
    logger.info("Global style applied")
