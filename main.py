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

from ui.main_window import MainWindow
from utils.style import detect_theme

# =============================================================================
# Logging Setup
# =============================================================================

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


# =============================================================================
# Font Setup
# =============================================================================

def setup_font() -> None:
    """
    Load and apply the Vazir font if available.
    Fallback to system font.
    """
    app = QApplication.instance()
    if not app:
        return

    # List of preferred fonts in order
    preferred_fonts = [
        "Vazir",
        "IRANSansWeb",
        "IRANSans",
        "Noto Sans",
        "Segoe UI",
        "system-ui",
        "sans-serif",
    ]

    # Check if any preferred font is available in the system
    font_families = QFontDatabase.families()
    chosen_font = None

    for font_name in preferred_fonts:
        if font_name in font_families:
            chosen_font = font_name
            break

    if chosen_font:
        font = QFont(chosen_font, 10)
        app.setFont(font)
        logging.info("Using font: %s", chosen_font)
    else:
        logging.info("No preferred font found, using system default")


# =============================================================================
# Main Application
# =============================================================================

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

    # Set application properties
    app.setApplicationName("FelfelDM")
    app.setOrganizationName("FelfelDM")
    app.setQuitOnLastWindowClosed(False)

    # Load modern font
    setup_font()

    # Set window icon
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_paths = [
        os.path.join(base_path, "logo", "icon256.png"),
        os.path.join(base_path, "logo", "icon128.png"),
        os.path.join(base_path, "logo", "icon64.png"),
    ]
    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            logging.info("Icon loaded from: %s", path)
            break

    # Do NOT apply theme here - it will be applied in MainWindow
    # to avoid double application and potential crashes

    # Create and show main window
    container = None  # Service container if used
    win = MainWindow(container)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
