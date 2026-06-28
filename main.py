#!/usr/bin/env python3
"""
FelfelDM - Download Manager
"""

import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.style import CustomProxyStyle, setup_style


def main() -> None:
    """Application entry point."""
    # High DPI support - use Round for better scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.Round
    )

    app = QApplication(sys.argv)

    # Set window icon
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_paths = [
        os.path.join(base_path, "logo/icon256.png"),
        os.path.join(base_path, "logo/icon128.png")
    ]

    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            break

    app.setStyle(CustomProxyStyle())
    app.setApplicationName("FelfelDM")
    app.setQuitOnLastWindowClosed(False)

    setup_style(app)

    win = MainWindow()
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
