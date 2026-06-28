# core/worker.py
import logging

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class BackendWorker(QThread):
    """Background worker for polling aria2 status using batch calls."""
    stats_updated = pyqtSignal(dict)

    def __init__(self, aria2, store):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True
        self.poll_interval = 1000  # milliseconds

    def run(self) -> None:
        """Main worker loop with batch polling."""
        while self.running:
            if not self.aria2.is_connected():
                self.stats_updated.emit({"connected": False})
                self.msleep(self.poll_interval)
                continue

            # Use batch call to reduce RPC requests
            results = self.aria2.batch_call([
                {"method": "aria2.getGlobalStat"},
                {"method": "aria2.tellActive"},
                {"method": "aria2.tellWaiting", "params": [0, 1000]},
                {"method": "aria2.tellStopped", "params": [0, 1000]},
            ])

            stat = {}
            active = []
            waiting = []
            stopped = []

            if len(results) >= 1 and isinstance(results[0], dict):
                stat = results[0] or {}
            if len(results) >= 2 and isinstance(results[1], list):
                active = results[1] or []
            if len(results) >= 3 and isinstance(results[2], list):
                waiting = results[2] or []
            if len(results) >= 4 and isinstance(results[3], list):
                stopped = results[3] or []

            self.stats_updated.emit({
                "connected": True,
                "stat": stat,
                "active": active,
                "waiting": waiting,
                "stopped": stopped,
            })
            self.msleep(self.poll_interval)

    def stop(self) -> None:
        """Stop the worker thread."""
        self.running = False
        self.quit()
        self.wait()
