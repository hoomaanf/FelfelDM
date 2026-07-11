# core/backend_worker.py

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from typing import Dict, Optional
import threading

# اضافه کردن import برای YouTubeWorker
from core.youtube_worker import YouTubeWorker
from core.data_store import DataStore


class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)
    size_fetched = pyqtSignal(str, int, str)
    
    # سیگنال‌های جدید برای دانلود یوتیوب
    youtube_progress = pyqtSignal(str, int)      # download_id, progress
    youtube_status = pyqtSignal(str, str)        # download_id, status
    youtube_speed = pyqtSignal(str, str, str)    # download_id, speed, eta
    youtube_finished = pyqtSignal(str, bool, str) # download_id, success, message

    def __init__(self, aria2, store: DataStore):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True
        self._fetching_sizes = set()
        self._fetched_sizes = set()
        
        # ===== بخش جدید: مدیریت دانلودهای یوتیوب =====
        self.youtube_workers: Dict[str, YouTubeWorker] = {}  # download_id -> worker
        self.youtube_downloads: Dict[str, dict] = {}  # download_id -> info
        self.youtube_lock = threading.Lock()
        
        # بارگذاری دانلودهای یوتیوب از دیتابیس
        self._load_youtube_downloads()
    
    def _load_youtube_downloads(self):
        """بارگذاری دانلودهای یوتیوب از دیتاستور"""
        try:
            # این رو باید بر اساس ساختار دیتاستورت بنویسی
            # فرض کن دیتاستور متدی داره به اسم get_youtube_downloads
            youtube_items = self.store.get_downloads_by_type('youtube')
            for item in youtube_items:
                download_id = item.get('id')
                if download_id:
                    self.youtube_downloads[download_id] = item
                    # اگر وضعیتش downloading یا paused بود، ادامه بده
                    if item.get('status') in ['downloading', 'paused']:
                        self._resume_youtube_download(item)
        except Exception as e:
            print(f"Error loading YouTube downloads: {e}")

    def run(self):
        loop_count = 0

        while self.running:
            loop_count += 1

            try:
                # ===== بخش aria2 (کدهای قبلی) =====
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

                # ===== بخش جدید: به‌روزرسانی دانلودهای یوتیوب =====
                youtube_status = self._get_youtube_status()
                
                self.stats_updated.emit(
                    {
                        "connected": True,
                        "stat": stat,
                        "downloads": downloads,
                        "active": active,
                        "waiting": waiting,
                        "stopped": stopped,
                        "youtube_downloads": youtube_status,  # اضافه کردن دانلودهای یوتیوب
                    }
                )

            except Exception as e:
                self.aria2_error.emit(str(e))
                self.stats_updated.emit({"connected": False})

            self.msleep(1000)

    def _get_youtube_status(self) -> list:
        """گرفتن وضعیت دانلودهای یوتیوب"""
        status_list = []
        with self.youtube_lock:
            for download_id, info in self.youtube_downloads.items():
                status_list.append({
                    'id': download_id,
                    'url': info.get('url', ''),
                    'title': info.get('yt_options', {}).get('title', ''),
                    'status': info.get('status', 'pending'),
                    'progress': info.get('progress', 0),
                    'speed': info.get('speed', ''),
                    'eta': info.get('eta', '')
                })
        return status_list

    def stop(self):
        self.running = False
        # توقف دانلودهای یوتیوب
        self._stop_all_youtube_downloads()
        if not self.wait(2000):
            self.terminate()

    # ===== بخش جدید: متدهای مدیریت دانلود یوتیوب =====
    
    def add_youtube_download(self, download_data: dict) -> str:
        """
        افزودن دانلود یوتیوب جدید
        
        Args:
            download_data: {
                'url': str,
                'save_path': str,
                'yt_options': {
                    'quality': str,
                    'format': str,
                    'cookies_path': Optional[str],
                    'subtitles': bool
                },
                'proxy': Optional[str],
                'queue_id': Optional[str]
            }
        Returns:
            download_id: str
        """
        import uuid
        from datetime import datetime
        
        download_id = str(uuid.uuid4())
        
        # ساخت آیتم دانلود
        download_item = {
            'id': download_id,
            'url': download_data['url'],
            'save_path': download_data['save_path'],
            'download_type': 'youtube',
            'status': 'pending',
            'progress': 0,
            'speed': '',
            'eta': '',
            'yt_options': download_data.get('yt_options', {}),
            'proxy': download_data.get('proxy'),
            'queue_id': download_data.get('queue_id'),
            'created_at': datetime.now().isoformat(),
            'completed_at': None,
            'error_message': ''
        }
        
        # ذخیره در دیتاستور
        self.store.save_download(download_item)
        
        # اضافه به دیکشنری
        with self.youtube_lock:
            self.youtube_downloads[download_id] = download_item
        
        # شروع دانلود
        self._start_youtube_download(download_id)
        
        return download_id
    
    def _start_youtube_download(self, download_id: str):
        """شروع دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                return
            
            item = self.youtube_downloads[download_id]
            
            # اگر در حال دانلود یا paused هست، نادیده بگیر
            if item.get('status') in ['downloading', 'completed']:
                return
            
            # ساخت worker
            worker = YouTubeWorker(
                url=item['url'],
                output_path=item['save_path'],
                format_type=item.get('yt_options', {}).get('format', 'mp4'),
                cookie_file=item.get('yt_options', {}).get('cookies_path'),
                proxy_url=item.get('proxy')
            )
            
            # اتصال سیگنال‌ها
            worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
            worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
            worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
            worker.finished.connect(lambda success, msg: self._on_youtube_finished(download_id, success, msg))
            
            # ذخیره worker
            self.youtube_workers[download_id] = worker
            
            # به‌روزرسانی وضعیت
            item['status'] = 'downloading'
            self.store.update_download_status(download_id, 'downloading')
            
            # شروع
            worker.start()
    
    def _resume_youtube_download(self, item: dict):
        """ادامه دانلود یوتیوب بعد از راه‌اندازی مجدد"""
        download_id = item['id']
        # مشابه _start_youtube_download ولی با وضعیت paused
        worker = YouTubeWorker(
            url=item['url'],
            output_path=item['save_path'],
            format_type=item.get('yt_options', {}).get('format', 'mp4'),
            cookie_file=item.get('yt_options', {}).get('cookies_path'),
            proxy_url=item.get('proxy')
        )
        
        worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
        worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
        worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
        worker.finished.connect(lambda success, msg: self._on_youtube_finished(download_id, success, msg))
        
        self.youtube_workers[download_id] = worker
        item['status'] = 'downloading'
        worker.start()
    
    def pause_youtube_download(self, download_id: str):
        """توقف موقت دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                if worker.is_running():
                    worker.pause()
                    if download_id in self.youtube_downloads:
                        self.youtube_downloads[download_id]['status'] = 'paused'
                        self.store.update_download_status(download_id, 'paused')
    
    def resume_youtube_download(self, download_id: str):
        """ادامه دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                if worker.is_running():
                    worker.resume()
                    if download_id in self.youtube_downloads:
                        self.youtube_downloads[download_id]['status'] = 'downloading'
                        self.store.update_download_status(download_id, 'downloading')
    
    def cancel_youtube_download(self, download_id: str):
        """لغو دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                if worker.is_running():
                    worker.cancel()
                del self.youtube_workers[download_id]
            
            if download_id in self.youtube_downloads:
                del self.youtube_downloads[download_id]
                self.store.delete_download(download_id)
    
    def _on_youtube_progress(self, download_id: str, progress: int):
        """دریافت پیشرفت دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]['progress'] = progress
                self.store.update_download_progress(download_id, progress)
        
        self.youtube_progress.emit(download_id, progress)
    
    def _on_youtube_status(self, download_id: str, status: str):
        """دریافت وضعیت دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]['status_text'] = status
        
        self.youtube_status.emit(download_id, status)
    
    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        """دریافت سرعت و زمان باقیمانده"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]['speed'] = speed
                self.youtube_downloads[download_id]['eta'] = eta
        
        self.youtube_speed.emit(download_id, speed, eta)
    
    def _on_youtube_finished(self, download_id: str, success: bool, message: str):
        """پایان دانلود یوتیوب"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                if success:
                    self.youtube_downloads[download_id]['status'] = 'completed'
                    self.youtube_downloads[download_id]['progress'] = 100
                    self.store.update_download_status(download_id, 'completed')
                else:
                    self.youtube_downloads[download_id]['status'] = 'error'
                    self.youtube_downloads[download_id]['error_message'] = message
                    self.store.update_download_status(download_id, 'error')
            
            # حذف worker
            if download_id in self.youtube_workers:
                del self.youtube_workers[download_id]
        
        self.youtube_finished.emit(download_id, success, message)
    
    def _stop_all_youtube_downloads(self):
        """توقف همه دانلودهای یوتیوب"""
        with self.youtube_lock:
            for download_id, worker in list(self.youtube_workers.items()):
                if worker.is_running():
                    worker.cancel()
            self.youtube_workers.clear()

    def _fetch_size_for_gid(self, gid: str, url: str):
        """دریافت حجم و کتگوری برای یک دانلود مشخص (کد قبلی)"""
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
                    filename = url.split("/")[-1].split("?")[0]

                category = get_category_from_filename(filename)
                self.size_fetched.emit(gid, size, category)
            else:
                print(f"⚠️⚠️⚠️ [BackendWorker] Could not fetch size for {gid}")

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            self._fetching_sizes.discard(gid)