#!/usr/bin/env python3
"""
FelfelDM - Download Manager with modern UI.
"""

import os
import sys
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtWidgets import QApplication

from core.service_container import get_container
from ui.main_window import MainWindow
from utils.style import detect_theme, apply_modern_theme


def setup_logging() -> None:
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def setup_font() -> None:
    """
    Load and apply a suitable font for the application.
    Tries to use system fonts, with fallback to default.
    """
    app = QApplication.instance()
    if not app:
        return

    # List of preferred fonts (first available will be used)
    preferred_fonts = [
        "Vazir",           # Popular Persian font
        "IRANSansWeb",     # Another Persian font
        "IRANSans",        # Alternative
        "Noto Sans",       # Google Noto Sans (covers many scripts)
        "Segoe UI",        # Windows default
        "system-ui",       # CSS generic
        "sans-serif",      # Final fallback
    ]

    font_family = None

    # Try to find a preferred font in the system
    available_families = QFontDatabase.families()
    for name in preferred_fonts:
        if name in available_families:
            font_family = name
            break

    # If no preferred font is found, use the default application font
    if font_family is None:
        font_family = app.font().family()
        logging.info("Using default system font: %s", font_family)
    else:
        logging.info("Using font: %s", font_family)

    # Create and apply the font
    font = QFont(font_family, 10)
    # Set default fallback for characters not in the font
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)


def main() -> None:
    """Application entry point."""
    setup_logging()

    # High DPI support - using modern approach
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )

    app = QApplication(sys.argv)

    # Use system default style instead of Fusion
    # app.setStyle('Fusion')  # Removed to use system default

    # Load modern font
    setup_font()

    # Set window icon
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_paths = [
        os.path.join(base_path, "logo/icon256.png"),
        os.path.join(base_path, "logo/icon128.png"),
    ]
    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            break

    app.setApplicationName("FelfelDM")
    app.setQuitOnLastWindowClosed(False)

    # Detect and apply modern theme
    is_dark = detect_theme()
    apply_modern_theme(app, is_dark)

    # Initialize the service container
    container = get_container()

    # Create main window with container
    win = MainWindow(container)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
