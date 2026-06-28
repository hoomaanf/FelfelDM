# main.py
"""
FelfelDM - Download Manager with modern UI.
"""

import os
import sys
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QFont, QIcon
from PyQt6.QtWidgets import QApplication

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


def main() -> None:
    """Application entry point."""
    setup_logging()

    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # Load modern font (Inter if available, otherwise fallback to system)
    font_id = QFontDatabase.addApplicationFont(":/fonts/Inter-Regular.ttf")
    if font_id != -1:
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        app.setFont(QFont(font_family, 10))
    else:
        app.setFont(QFont("Segoe UI", 10))

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

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
