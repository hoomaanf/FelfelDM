from PyQt6.QtCore import QThread, pyqtSignal

class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)

    def __init__(self, aria2, store):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True

    def run(self):
        while self.running:
            try:
                if not self.aria2.is_connected():
                    if not self.aria2.start_aria2():
                        self.stats_updated.emit({"connected": False})
                        self.msleep(2000)
                        continue

                stat = self.aria2.get_global_stat() or {}
                active = self.aria2.tell_active() or []
                waiting = self.aria2.tell_waiting() or []
                stopped = self.aria2.tell_stopped(0, 300) or [] 

                downloads = active + waiting + stopped

                for d in list(downloads)[:25]:
                    gid = d.get("gid")
                    if gid and d.get("status") in ("active", "waiting"):
                        full = self.aria2.tell_status(gid)
                        if full:
                            for i, item in enumerate(downloads):
                                if item.get("gid") == gid:
                                    downloads[i] = full
                                    break

                self.stats_updated.emit({
                    "connected": True,
                    "stat": stat,
                    "downloads": downloads,
                    "active": active,
                    "waiting": waiting,
                    "stopped": stopped,
                })

            except Exception as e:
                self.aria2_error.emit(str(e))
                self.stats_updated.emit({"connected": False})

            self.msleep(1000)

    def stop(self):
        """توقف تمیز worker"""
        self.running = False
        if not self.wait(2000): 
            self.terminate()