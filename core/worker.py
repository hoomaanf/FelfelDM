# core/worker.py
from PyQt6.QtCore import QThread, pyqtSignal

class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)

    def __init__(self, aria2, store):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True

    def run(self):
        while self.running:
            if not self.aria2.is_connected():
                self.stats_updated.emit({"connected": False})
                self.msleep(1000)
                continue

            stat = self.aria2.get_global_stat() or {}
            active = self.aria2.tell_active() or []
            waiting = self.aria2.tell_waiting() or []
            stopped = self.aria2.tell_stopped() or []

            self.stats_updated.emit({
                "connected": True,
                "stat": stat,
                "active": active,
                "waiting": waiting,
                "stopped": stopped,
            })
            self.msleep(1000)