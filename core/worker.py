from PyQt6.QtCore import QThread, pyqtSignal,QTimer

class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)
    size_fetched = pyqtSignal(str, int, str)

    def __init__(self, aria2, store):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True
        self._fetching_sizes = set()
        self._fetched_sizes = set()

    def run(self):
        loop_count = 0
        
        while self.running:
            loop_count += 1
            
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

                for d in downloads:
                    gid = d.get("gid")
                    if not gid:
                        continue
                        
                    if gid in self._fetching_sizes:
                        continue
                    
                    total = int(d.get("totalLength", 0))
                    status = d.get("status", "")
                    
                    if total == 0 and status in ("active", "waiting", "paused"):
                        files = d.get("files", [])
                        url = None
                        if files and files[0].get("uris"):
                            uris = files[0].get("uris", [])
                            if uris and uris[0].get("uri"):
                                url = uris[0].get("uri")
                        
                        if url:
                            self._fetching_sizes.add(gid)
                            self._fetch_size_for_gid(gid, url)

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
        self.running = False
        if not self.wait(2000): 
            self.terminate()
            
    def _fetch_size_for_gid(self, gid: str, url: str):
        """دریافت حجم و کتگوری برای یک دانلود مشخص"""
        if gid in self._fetched_sizes:
            return
        
        try:
            from core.file_size_fetcher import get_file_size
            from utils.helpers import get_category_from_filename
            
            size = get_file_size(url, timeout=10)
            if size and size > 0:
                self._fetched_sizes.add(gid)
                
                filename = None
                for q in self.store.queues:
                    if gid in q.downloads_info:
                        filename = q.downloads_info[gid].get("name", "")
                        break
                
                if not filename:
                    filename = url.split('/')[-1].split('?')[0]
                
                category = get_category_from_filename(filename)
                self.size_fetched.emit(gid, size, category)
            else:
                print(f"⚠️⚠️⚠️ [BackendWorker] Could not fetch size for {gid}")
                
        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            self._fetching_sizes.discard(gid)