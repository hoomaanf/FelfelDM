# Requires: PyQt6>=6.4.0
# Requires: requests>=2.28.0
# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0
# Requires: websocket-client>=1.4.0
# Requires: cryptography>=38.0.0
# Requires: packaging>=21.0

"""
Entry point for FelfelDM Download Manager.
"""

import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import NoReturn

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from utils.style import apply_style
from ui.main_window import MainWindow
from core.aria2_manager import Aria2Manager
from core.data_store import DataStore
from core.session_manager import SessionManager


def configure_logging() -> None:
    """Configure logging for the entire application with rotation and levels."""
    log_dir: Path = Path.home() / ".cache" / "felfelDM" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file: Path = log_dir / "felfelDM.log"

    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler for INFO and above
    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format: logging.Formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler for DEBUG and above with rotation
    file_handler: RotatingFileHandler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_format: logging.Formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    # Quiet noisy libraries
    for lib in ('urllib3', 'keyring', 'websocket', 'requests'):
        logging.getLogger(lib).setLevel(logging.WARNING)


def main() -> NoReturn:
    """Main application entry point."""
    configure_logging()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)

    apply_style(app)

    # Initialize data store and session manager early
    store: DataStore = DataStore()
    session_mgr: SessionManager = SessionManager(store)

    # Start aria2 subprocess
    aria2_manager: Aria2Manager = Aria2Manager()
    if not aria2_manager.start():
        logging.critical("Failed to start aria2. Exiting.")
        sys.exit(1)

    window: MainWindow = MainWindow(aria2_manager, store, session_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
