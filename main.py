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
    Load and apply the Inter font if available.
    Fallback to system font.
    """
    # Try to load Inter font from local resources
    font_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Inter-Regular.ttf"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts", "Inter-Variable.ttf"),
    ]

    font_family = None
    for path in font_paths:
        if os.path.exists(path):
            font_id = QFontDatabase.addApplicationFont(path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    font_family = families[0]
                    break

    # If Inter not found, use system font
    if font_family is None:
        # Try to use Inter from system if available
        if "Inter" in QFontDatabase.families():
            font_family = "Inter"
        else:
            # Fallback to Segoe UI or system default
            font_family = "Segoe UI" if sys.platform == "win32" else "sans-serif"

    app = QApplication.instance()
    if app:
        font = QFont(font_family, 10)
        app.setFont(font)
        logging.info("Font loaded: %s", font_family)


def main() -> None:
    """Application entry point."""
    setup_logging()

    # High DPI support - using modern approach
    # Note: AA_EnableHighDpiScaling and AA_UseHighDpiPixmaps are not needed in PyQt6
    # when using setHighDpiScaleFactorRoundingPolicy.
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )

    app = QApplication(sys.argv)

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
