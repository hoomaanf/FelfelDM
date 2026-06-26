# core/worker.py

from PyQt6.QtCore import QThread, pyqtSignal
from datetime import datetime

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

            try:
                max_concurrent = self.store.settings.get("max_concurrent", 5)
                self.aria2.change_global_option({"max-concurrent-downloads": str(max_concurrent)})
            except:
                pass

            stat = self.aria2.get_global_stat() or {}
            active = self.aria2.tell_active() or []
            waiting = self.aria2.tell_waiting() or []
            stopped = self.aria2.tell_stopped() or []

            all_server_states = {d['gid']: d['status'] for d in (active + waiting + stopped)}

            now_time = datetime.now().time().replace(second=0, microsecond=0)
            now_day = datetime.now().weekday()

            status_changed = False

            for queue in self.store.queues:
                # ─── همه GIDهایی که توی all_server_states هستن رو نگه دار ────
                # اما اگه GID جدیدی هست که توی queue.downloads نیست، اضافه کن
                current_gids = set(queue.downloads)
                server_gids = set(all_server_states.keys())       
                
                # GIDهایی که توی سرور نیستن رو حذف کن
                queue.downloads = [g for g in queue.downloads if g in all_server_states]
                
                is_scheduled_time = queue.is_scheduled_now()
                
                # اگر صف Pause هست یا زمانش نیست
                if queue.paused or not is_scheduled_time:
                    for g in queue.downloads:
                        if all_server_states.get(g) == 'active':
                            self.aria2.pause(g)
                            status_changed = True
                    continue

                # اگر زمان هست و صف Pause نیست، Resume کن
                q_active = sum(1 for g in queue.downloads if all_server_states.get(g) == 'active')
                if q_active < queue.max_concurrent:
                    slots = queue.max_concurrent - q_active
                    for g in queue.downloads:
                        if slots <= 0:
                            break
                        if all_server_states.get(g) == 'paused':
                            self.aria2.resume(g)
                            status_changed = True
                            slots -= 1

            self.stats_updated.emit({
                "connected": True, 
                "stat": stat,
                "active": active, 
                "waiting": waiting, 
                "stopped": stopped,
                "status_changed": status_changed
            })
            self.msleep(1000)