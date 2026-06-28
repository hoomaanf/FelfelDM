# Requires: PyQt6>=6.4.0
# Requires: requests>=2.28.0
# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0
# Requires: websocket-client>=1.4.0
# Requires: cryptography>=38.0.0
# Requires: packaging>=21.0

"""Entry point for FelfelDM Download Manager."""

import sys
import logging
import shutil
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

__version__ = "3.0.0"


def configure_logging() -> None:
    log_dir: Path = Path.home() / ".cache" / "felfelDM" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file: Path = log_dir / "felfelDM.log"

    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    file_handler: RotatingFileHandler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    for lib in ("urllib3", "keyring", "websocket", "requests"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def find_aria2_binary() -> Path | None:
    aria2_path = shutil.which("aria2c")
    if aria2_path:
        return Path(aria2_path)

    common_paths = []
    if sys.platform == "win32":
        common_paths = [
            Path("C:/Program Files/aria2/aria2c.exe"),
            Path("C:/Program Files (x86)/aria2/aria2c.exe"),
        ]
    elif sys.platform == "darwin":
        common_paths = [
            Path("/usr/local/bin/aria2c"),
            Path("/opt/homebrew/bin/aria2c"),
        ]
    else:
        common_paths = [
            Path("/usr/bin/aria2c"),
            Path("/usr/local/bin/aria2c"),
        ]

    for path in common_paths:
        if path.exists() and path.is_file():
            return path
    return None


def main() -> NoReturn:
    configure_logging()
    logger = logging.getLogger(__name__)

    aria2_binary = find_aria2_binary()
    if aria2_binary is None:
        logger.critical("aria2c binary not found.")
        print("\n" + "=" * 60)
        print("ERROR: aria2c binary not found!")
        print("Please install aria2 from: https://aria2.github.io/")
        print("Make sure 'aria2c' is available in your PATH.")
        print("=" * 60 + "\n")
        sys.exit(1)

    logger.info("Found aria2c at: %s", aria2_binary)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    apply_style(app)

    store: DataStore = DataStore()
    session_mgr: SessionManager = SessionManager(store)

    aria2_manager: Aria2Manager = Aria2Manager(aria2_binary_path=aria2_binary)
    if not aria2_manager.start():
        logger.critical("Failed to start aria2. Exiting.")
        sys.exit(1)

    window: MainWindow = MainWindow(aria2_manager, store, session_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
