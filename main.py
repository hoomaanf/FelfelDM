# =============================================================================
# main.py
# =============================================================================
import sys
import logging
import argparse
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFontDatabase, QFont

from core.aria2_manager import start_aria2, _get_secret_from_file
from core.data_store import DataStore
from core.worker import SyncBackendWorker
from core.local_server import LocalServer
from ui.main_window import MainWindow
from utils.style import setup_style, setup_font

logger = logging.getLogger(__name__)


def setup_logging(level: int = logging.INFO) -> None:
    log_dir = Path.home() / ".felfeldm"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "felfeldm.log")
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="FelfelDM Download Manager")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL verification (not recommended)")
    args = parser.parse_args()

    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level)

    # Create application first
    app = QApplication(sys.argv)

    # Setup font and style
    setup_font(app)
    setup_style(app)

    # Load data
    store = DataStore()

    # Get or start aria2
    secret = store.settings.aria2_secret
    if not secret:
        secret = _get_secret_from_file() or "felfeldm-secret"
        store.settings.aria2_secret = secret
        store.save()

    # Start aria2
    success = start_aria2(
        secret,
        rpc_port=6800,
        download_dir=store.settings.download_dir,
        speed_limit=store.settings.speed_limit
    )
    if not success:
        logger.critical("Failed to start aria2. Please ensure aria2 is installed and in PATH.")
        QMessageBox.critical(None, "Error", "Failed to start aria2. Please install aria2 and try again.")
        sys.exit(1)

    # Initialize RPC and worker (sync mode)
    from core.aria2_rpc import Aria2RPC
    rpc = Aria2RPC(
        host="127.0.0.1",
        port=6800,
        secret=secret,
        verify_ssl=not args.no_verify_ssl
    )
    worker = SyncBackendWorker(rpc, store)

    # Start local server for browser extension
    local_server = LocalServer(host="127.0.0.1", port=8080)
    local_server.start()

    # Create main window
    window = MainWindow(worker, store, local_server)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
