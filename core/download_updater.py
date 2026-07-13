from PyQt6.QtCore import QThread, pyqtSignal
import time
from typing import Optional
from core.aria2_rpc import Aria2RPC
from core.temp_db import TempDB

class DownloadUpdaterThread(QThread):
    """Thread برای به‌روزرسانی خودکار دانلودها"""
    
    download_updated = pyqtSignal(dict)  # Signal برای به‌روزرسانی UI
    
    def __init__(self, aria2: Aria2RPC, temp_db: TempDB, interval: float = 0.5):
        super().__init__()
        self.aria2 = aria2
        self.temp_db = temp_db
        self.interval = interval
        self._running = True
    
    def run(self):
        """حلقه اصلی به‌روزرسانی"""
        while self._running:
            try:
                if self.aria2.is_connected():
                    active = self.aria2.tell_active()
                    waiting = self.aria2.tell_waiting()
                    stopped = self.aria2.tell_stopped()
                    
                    all_downloads = active + waiting + stopped
                    for dl in all_downloads:
                        gid = dl.get('gid')
                        if gid:
                            status = dl.get('status', 'unknown')
                            progress = self._calc_progress(dl)
                            speed = int(dl.get('downloadSpeed', 0))
                            
                            self.temp_db.update_download_status(
                                gid=gid,
                                status=status,
                                progress=progress,
                                speed=speed,
                                name=dl.get('name', 'Unknown')
                            )
                            
                            self.download_updated.emit({
                                'gid': gid,
                                'status': status,
                                'progress': progress,
                                'speed': speed,
                                'name': dl.get('name', 'Unknown'),
                                'totalLength': int(dl.get('totalLength', 0)),
                                'completedLength': int(dl.get('completedLength', 0))
                            })
                
                time.sleep(self.interval)
            except Exception as e:
                print(f"⚠️ Updater error: {e}")
                time.sleep(self.interval)
    
    def _calc_progress(self, dl: dict) -> int:
        """محاسبه پیشرفت دانلود به درصد"""
        total = int(dl.get('totalLength', 0))
        completed = int(dl.get('completedLength', 0))
        if total > 0:
            return int((completed / total) * 100)
        return 0
    
    def stop(self):
        """توقف Thread"""
        self._running = False
        self.wait()