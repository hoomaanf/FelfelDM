# =============================================================================
# main.py
# =============================================================================
import sys
import logging
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QFont

from core.aria2_manager import start_aria2, _get_secret_from_file
from core.data_store import DataStore
from core.worker import BackendWorker
from core.local_server import LocalServer
from ui.main_window import MainWindow
from utils.style import setup_style, setup_font

logger = logging.getLogger(__name__)

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(Path.home() / ".felfeldm" / "felfeldm.log")
        ]
    )

def main() -> None:
    setup_logging()

    # Create application first
    app = QApplication(sys.argv)

    # Now setup font
    setup_font(app)

    # Load data
    store = DataStore()

    # Get or start aria2
    secret = store.settings.aria2_secret
    if not secret:
        secret = _get_secret_from_file() or "felfeldm-secret"
        store.settings.aria2_secret = secret
        store.save()

    start_aria2(secret, rpc_port=6800, download_dir=store.settings.download_dir)

    # Initialize worker
    from core.aria2_rpc import Aria2RPC
    rpc = Aria2RPC(host="127.0.0.1", port=6800, secret=secret, verify_ssl=False)
    worker = BackendWorker(rpc, store, async_mode=False)

    # Start local server for browser extension
    local_server = LocalServer(host="127.0.0.1", port=8080)
    local_server.start()

    # Create main window
    window = MainWindow(worker, store, local_server)
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
