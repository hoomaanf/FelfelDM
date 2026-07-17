# core/worker.py

from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from typing import Dict, Optional, List, Set
import threading
import uuid
from datetime import datetime
import os
import time

from core.youtube_worker import YouTubeWorker
from core.data_store import DataStore


class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)
    size_fetched = pyqtSignal(str, int, str)

    youtube_progress = pyqtSignal(str, int)  # download_id, progress
    youtube_status = pyqtSignal(str, str)  # download_id, status
    youtube_speed = pyqtSignal(str, str, str)  # download_id, speed, eta
    youtube_finished = pyqtSignal(str, bool, str)  # download_id, success, message
    youtube_size_fetched = pyqtSignal(str, int)  # download_id, size

    def __init__(self, aria2, store: DataStore):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True
        
        # Track size fetching state
        self._fetching_sizes: Set[str] = set()
        self._fetched_sizes: Set[str] = set()
        
        # YouTube download management
        self.youtube_workers: Dict[str, YouTubeWorker] = {}
        self.youtube_downloads: Dict[str, dict] = {}
        self.youtube_lock = threading.Lock()
        self.youtube_gids: Set[str] = set()
        self._size_workers: Dict[str, YouTubeWorker] = {}
        
        # Cache for aria2 download states
        self._download_cache: Dict[str, dict] = {}
        self._last_update_time: Dict[str, float] = {}
        self._CACHE_TTL = 0.1
        
        self._load_youtube_downloads()

    def _load_youtube_downloads(self):
        """Load YouTube downloads from datastore"""
        try:
            youtube_items = self.store.get_all_youtube_downloads()
            for item in youtube_items:
                download_id = item.get("id")
                if download_id:
                    self.youtube_downloads[download_id] = item
                    self.youtube_gids.add(download_id)

                    status = item.get("status", "")
                    print(f"📁 Loading YouTube download: {download_id} - status: {status}")

                    if status in ["completed", "cancelled"]:
                        self.store.delete_youtube_download(download_id)
                        if download_id in self.youtube_downloads:
                            del self.youtube_downloads[download_id]
                        self.youtube_gids.discard(download_id)
                        print(f"🗑️ Removed completed/cancelled download: {download_id}")
                        continue

                    if status in ["downloading", "paused"]:
                        self.youtube_downloads[download_id]["status"] = "paused"
                        self.store.update_youtube_status(download_id, "paused")
                        print(f"⏸️ Set download to paused: {download_id}")

            self._cleanup_completed_downloads()
            print(f"📁 Loaded {len(self.youtube_downloads)} active YouTube downloads")

        except Exception as e:
            print(f"Error loading YouTube downloads: {e}")
            import traceback
            traceback.print_exc()

    def _cleanup_completed_downloads(self):
        """Clean up completed and cancelled downloads from datastore"""
        try:
            all_downloads = self.store.get_all_youtube_downloads()
            for item in all_downloads:
                download_id = item.get("id")
                status = item.get("status", "")
                if status in ["completed", "cancelled"]:
                    self.store.delete_youtube_download(download_id)
                    print(f"🗑️ Cleaned up completed/cancelled: {download_id}")
        except Exception as e:
            print(f"Error cleaning up downloads: {e}")

    def cancel_youtube_download_without_delete(self, download_id: str):
        """Cancel YouTube download without deleting files"""
        print(f"🗑️ [Worker] Cancelling YouTube download without delete: {download_id}")

        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                del self.youtube_workers[download_id]

        if worker and worker.is_running():
            worker.cancel()
            worker.wait(1000)

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                del self.youtube_downloads[download_id]
            self.youtube_gids.discard(download_id)

            if download_id in self._size_workers:
                try:
                    size_worker = self._size_workers[download_id]
                    if size_worker.isRunning():
                        size_worker.quit()
                        size_worker.wait(1000)
                except:
                    pass
                del self._size_workers[download_id]

        print(f"🗑️ [Worker] YouTube download cancelled (files kept): {download_id}")

    def run(self):
        """Main polling loop - builds complete runtime snapshot of all downloads"""
        while self.running:
            try:
                # Ensure aria2 is connected
                if not self.aria2.is_connected():
                    if not self.aria2.start_aria2():
                        self.stats_updated.emit({"connected": False})
                        self.msleep(100)
                        continue

                # Build complete runtime snapshot
                snapshot = self._build_runtime_snapshot()
                
                # Emit the complete snapshot
                self.stats_updated.emit(snapshot)

            except Exception as e:
                self.aria2_error.emit(str(e))
                self.stats_updated.emit({"connected": False})

            self.msleep(100)

    def _build_runtime_snapshot(self) -> dict:
        """Build complete runtime snapshot of all aria2 downloads"""
        # Get all downloads from aria2
        active = self.aria2.tell_active() or []
        waiting = self.aria2.tell_waiting() or []
        stopped = self.aria2.tell_stopped(0, 300) or []
        
        # Combine all downloads
        all_downloads = active + waiting + stopped
        
        # Build the complete download list with full details
        downloads_snapshot = []
        seen_gids = set()
        
        # Process each download
        for download in all_downloads:
            gid = download.get("gid")
            if not gid or gid in seen_gids:
                continue
            seen_gids.add(gid)
            
            # Get complete download info
            complete_info = self._get_complete_download_info(gid, download)
            if complete_info:
                downloads_snapshot.append(complete_info)
        
        # Get YouTube status
        try:
            youtube_status = self._get_youtube_status()
            if not isinstance(youtube_status, list):
                youtube_status = []
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            youtube_status = []
        
        # Build complete snapshot
        snapshot = {
            "connected": True,
            "stat": self.aria2.get_global_stat() or {},
            "downloads": downloads_snapshot,
            "active": active,
            "waiting": waiting,
            "stopped": stopped,
            "youtube_downloads": youtube_status,
        }
        
        return snapshot

    def _get_complete_download_info(self, gid: str, partial_info: dict) -> Optional[dict]:
        """Get complete download information for a single gid"""
        # Check cache first
        current_time = time.time()
        if gid in self._download_cache and (current_time - self._last_update_time.get(gid, 0)) < self._CACHE_TTL:
            cached = self._download_cache[gid].copy()
            # Update status if it changed
            if partial_info.get("status") != cached.get("status"):
                cached["status"] = partial_info.get("status")
            return cached
        
        try:
            # Get full status from aria2
            full_info = self.aria2.tell_status(gid)
            if not full_info:
                # Use partial info as fallback
                full_info = partial_info
            
            # Ensure all required fields are present
            complete_info = {
                "gid": gid,
                "status": full_info.get("status", "unknown"),
                "totalLength": full_info.get("totalLength", "0"),
                "completedLength": full_info.get("completedLength", "0"),
                "downloadSpeed": full_info.get("downloadSpeed", "0"),
                "files": full_info.get("files", []),
                "connections": full_info.get("connections", "0"),
                "errorMessage": full_info.get("errorMessage", ""),
            }
            
            # Add optional fields that might be useful
            optional_fields = [
                "uploadLength", "uploadSpeed", "bitfield",
                "bittorrent", "verifiedLength", "verifyIntegrityPending",
                "seeder", "numSeeders", "pieceLength", "totalPieces",
                "dir", "infoHash", "numPieces"
            ]
            for field in optional_fields:
                if field in full_info:
                    complete_info[field] = full_info[field]
            
            # Store in cache
            self._download_cache[gid] = complete_info
            self._last_update_time[gid] = time.time()
            
            # Trigger size fetch if needed
            if complete_info.get("totalLength") == "0" and complete_info.get("status") in ("active", "waiting", "paused"):
                if gid not in self.youtube_gids and gid not in self._fetching_sizes and gid not in self._fetched_sizes:
                    files = complete_info.get("files", [])
                    url = None
                    if files and files[0].get("uris"):
                        uris = files[0].get("uris", [])
                        if uris and uris[0].get("uri"):
                            url = uris[0].get("uri")
                    if url:
                        self._fetching_sizes.add(gid)
                        self._fetch_size_for_gid(gid, url)
            
            return complete_info
            
        except Exception as e:
            print(f"⚠️ Error getting complete info for {gid}: {e}")
            # Return basic info
            return {
                "gid": gid,
                "status": partial_info.get("status", "unknown"),
                "totalLength": partial_info.get("totalLength", "0"),
                "completedLength": partial_info.get("completedLength", "0"),
                "downloadSpeed": partial_info.get("downloadSpeed", "0"),
                "files": partial_info.get("files", []),
                "connections": partial_info.get("connections", "0"),
                "errorMessage": partial_info.get("errorMessage", ""),
            }

    def _get_youtube_status(self) -> List[dict]:
        """Get status of YouTube downloads"""
        status_list = []
        try:
            with self.youtube_lock:
                for download_id, info in self.youtube_downloads.items():
                    status_list.append({
                        "id": download_id,
                        "url": info.get("url", ""),
                        "title": info.get("yt_options", {}).get("title", ""),
                        "status": info.get("status", "pending"),
                        "progress": info.get("progress", 0),
                        "speed": info.get("speed", ""),
                        "eta": info.get("eta", ""),
                        "total_size": info.get("total_size", 0),
                    })
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            return []
        
        return status_list

    def stop(self):
        self.running = False
        self._stop_all_youtube_downloads()
        self._stop_all_size_workers()
        if not self.wait(2000):
            self.terminate()

    def _stop_all_size_workers(self):
        """Stop all size fetching workers"""
        for download_id, worker in list(self._size_workers.items()):
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1000)
            except:
                pass
        self._size_workers.clear()

    def add_youtube_download(self, download_data: dict) -> str:
        print(f"🔥🔥🔥 add_youtube_download CALLED")
        print(f"🔥🔥🔥 download_data: {download_data}")

        download_id = download_data.get("id") or str(uuid.uuid4())

        existing = self.store.get_youtube_download(download_id)

        if existing:
            print(f"📦 [ADD] Download already exists: {download_id}")

            with self.youtube_lock:
                self.youtube_downloads[download_id] = existing
                self.youtube_gids.add(download_id)
                total_size = existing.get("total_size", 0)

            if total_size > 0:
                print(f"📏 [ADD] Size already fetched: {total_size}")
                self._start_youtube_download(download_id)
            else:
                self._fetch_youtube_size(download_id)

            return download_id

        download_item = {
            "id": download_id,
            "url": download_data["url"],
            "save_path": download_data["save_path"],
            "download_type": "youtube",
            "status": "paused",
            "progress": 0,
            "speed": "",
            "eta": "",
            "total_size": 0,
            "yt_options": download_data.get("yt_options", {}),
            "proxy": download_data.get("proxy"),
            "queue_id": download_data.get("queue_id"),
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "error_message": "",
        }

        self.store.add_youtube_download(download_item)

        with self.youtube_lock:
            self.youtube_downloads[download_id] = download_item
            self.youtube_gids.add(download_id)

        self._fetch_youtube_size(download_id)

        return download_id

    def _fetch_youtube_size(self, download_id: str):
        """Fetch YouTube download size using yt-dlp"""
        print(f"📏📏📏 _fetch_youtube_size CALLED")
        print(f"📏📏📏 download_id: {download_id}")

        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                print(f"⚠️ [SIZE] Download {download_id} not found")
                return

            item = self.youtube_downloads[download_id]

            if item.get("total_size", 0) > 0:
                print(f"📏 [SIZE] Size already fetched: {item['total_size']}")
                return

            url = item["url"]
            save_path = item["save_path"]
            format_type = item.get("yt_options", {}).get("format", "mp4")
            cookie_file = item.get("yt_options", {}).get("cookies_path")
            proxy_url = item.get("proxy")

        print(f"🔍 [SIZE] Fetching size for: {download_id}")
        print(f"🔍 [SIZE] URL: {url}")
        print(f"🔍 [SIZE] Proxy: {proxy_url}")
        print(f"🔍 [SIZE] Cookies: {cookie_file}")

        size_worker = YouTubeWorker(
            url=url,
            output_path=save_path,
            format_type=format_type,
            cookie_file=cookie_file,
            proxy_url=proxy_url,
        )

        size_worker.size_fetched.connect(
            lambda size: self._on_youtube_size_fetched(download_id, size)
        )

        size_worker.is_fetching_size = True
        size_worker.start()

        self._size_workers[download_id] = size_worker
        print(f"📏 [SIZE] Worker started for: {download_id}")

    def _on_youtube_size_fetched(self, download_id: str, size: int):
        """Handle YouTube size fetch completion"""
        print(f"📏 [SIZE] Received size for {download_id}: {size} bytes")

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["total_size"] = size
                self.youtube_downloads[download_id]["status"] = "paused"
                self.store.update_youtube_download(
                    download_id,
                    {"total_size": size, "status": "paused"},
                )
                print(f"📏 [SIZE] Updated store: {size} bytes, status: paused")

        self.youtube_size_fetched.emit(download_id, size)

        if download_id in self._size_workers:
            try:
                worker = self._size_workers[download_id]
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1000)
            except:
                pass
            del self._size_workers[download_id]
            print(f"📏 [SIZE] Cleaned up worker")

    def _start_youtube_download(self, download_id: str):
        """Start actual YouTube download (after size is fetched)"""
        print(f"🎬🎬🎬 _start_youtube_download CALLED for: {download_id}")

        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                print(f"⚠️ [START] Download {download_id} not found")
                return

            item = self.youtube_downloads[download_id]

            total_size = item.get("total_size", 0)
            print(f"📏 [START] total_size for {download_id}: {total_size}")

            if total_size == 0:
                print(f"📏 [START] Size not fetched, fetching first...")
                pass
            else:
                if item.get("status") in ["downloading", "completed"]:
                    print(f"⏭️ [START] Already {item.get('status')}")
                    return

                url = item["url"]
                save_path = item["save_path"]
                format_type = item.get("yt_options", {}).get("format", "mp4")
                cookie_file = item.get("yt_options", {}).get("cookies_path")
                proxy_url = item.get("proxy")

        if total_size == 0:
            self._fetch_youtube_size(download_id)
            return

        print(f"🎬 [START] Creating YouTubeWorker for {download_id}")
        worker = YouTubeWorker(
            url=url,
            output_path=save_path,
            format_type=format_type,
            cookie_file=cookie_file,
            proxy_url=proxy_url,
        )

        worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
        worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
        worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
        worker.finished.connect(
            lambda success, msg: self._on_youtube_finished(download_id, success, msg)
        )

        with self.youtube_lock:
            self.youtube_workers[download_id] = worker
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["status"] = "downloading"
                self.store.update_youtube_status(download_id, "downloading")

        self.youtube_status.emit(download_id, "downloading")

        print(f"🎬 [START] Calling worker.start() for {download_id}")
        worker.start()
        print(f"🎬 YouTube download started: {download_id}")

    def _resume_youtube_download(self, item: dict):
        """Resume YouTube download after restart"""
        download_id = item["id"]
        worker = YouTubeWorker(
            url=item["url"],
            output_path=item["save_path"],
            format_type=item.get("yt_options", {}).get("format", "mp4"),
            cookie_file=item.get("yt_options", {}).get("cookies_path"),
            proxy_url=item.get("proxy"),
        )

        worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
        worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
        worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
        worker.finished.connect(
            lambda success, msg: self._on_youtube_finished(download_id, success, msg)
        )

        self.youtube_workers[download_id] = worker
        item["status"] = "downloading"
        self.store.update_youtube_status(download_id, "downloading")
        worker.start()
        print(f"🎬 YouTube download resumed: {download_id}")

    def pause_youtube_download(self, download_id: str):
        """Pause YouTube download"""
        print(f"⏸️ [Worker] Pausing: {download_id}")

        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]

        if worker and worker.is_running():
            worker.pause()
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    self.youtube_downloads[download_id]["status"] = "paused"
                    self.store.update_youtube_status(download_id, "paused")
            self.youtube_status.emit(download_id, "paused")
            print(f"⏸️ [Worker] Paused and signal sent: {download_id}")

    def resume_youtube_download(self, download_id: str):
        """Resume YouTube download"""
        print(f"▶️ [Worker] Resuming: {download_id}")

        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]

        if worker and worker.is_running():
            worker.resume()
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    self.youtube_downloads[download_id]["status"] = "downloading"
                    self.store.update_youtube_status(download_id, "downloading")
            self.youtube_status.emit(download_id, "downloading")
            print(f"▶️ [Worker] Resumed and signal sent: {download_id}")

    def cancel_youtube_download(self, download_id: str):
        """Cancel YouTube download and delete incomplete files"""
        print(f"🗑️ [Worker] Cancelling YouTube download: {download_id}")

        worker = None
        file_path = None
        save_path = None

        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                del self.youtube_workers[download_id]

            if download_id in self.youtube_downloads:
                yt_options = self.youtube_downloads[download_id].get("yt_options", {})
                title = yt_options.get("title", "Unknown")
                format_type = yt_options.get("format", "video")
                ext = "mp4" if format_type == "video" else "mp3"

                import re
                filename = re.sub(r'[<>:"/\\|?*]', "_", title)
                full_filename = f"{filename}.{ext}"

                save_path = self.youtube_downloads[download_id].get("save_path", "")
                file_path = os.path.join(save_path, full_filename)

        if worker and worker.is_running():
            worker.cancel()
            worker.wait(1000)

        if file_path and save_path:
            self._delete_youtube_files(file_path, save_path, title)

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                del self.youtube_downloads[download_id]
            self.youtube_gids.discard(download_id)

            if download_id in self._size_workers:
                try:
                    size_worker = self._size_workers[download_id]
                    if size_worker.isRunning():
                        size_worker.quit()
                        size_worker.wait(1000)
                except:
                    pass
                del self._size_workers[download_id]

        print(f"🗑️ [Worker] YouTube download cancelled and files deleted: {download_id}")

    def _delete_youtube_files(self, file_path: str, save_path: str, title: str):
        """Delete YouTube download files (complete and partial)"""
        try:
            import glob
            import re

            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Deleted: {file_path}")

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            patterns = [
                f"{base_name}.*.part",
                f"{base_name}.*.ytdl",
                f"{base_name}.*.f*",
                f"{base_name}.*.temp",
                f"{base_name}.*.download",
            ]

            for pattern in patterns:
                full_pattern = os.path.join(save_path, pattern)
                for f in glob.glob(full_pattern):
                    try:
                        os.remove(f)
                        print(f"🗑️ Deleted partial: {f}")
                    except:
                        pass

            safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
            partial_patterns = [
                f"{safe_title}.*.part",
                f"{safe_title}.*.ytdl",
                f"{safe_title}.*.f*",
                f"{safe_title}.*.temp",
                f"{safe_title}.*.download",
            ]

            for pattern in partial_patterns:
                full_pattern = os.path.join(save_path, pattern)
                for f in glob.glob(full_pattern):
                    try:
                        os.remove(f)
                        print(f"🗑️ Deleted partial (title): {f}")
                    except:
                        pass

        except Exception as e:
            print(f"⚠️ Error deleting files: {e}")

    def _on_youtube_progress(self, download_id: str, progress: int):
        """Handle YouTube download progress"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["progress"] = progress
                self.store.update_youtube_progress(download_id, progress)

        self.youtube_progress.emit(download_id, progress)

    def _on_youtube_status(self, download_id: str, status: str):
        """Handle YouTube download status"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["status_text"] = status

        self.youtube_status.emit(download_id, status)

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        """Handle YouTube download speed and ETA"""
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["speed"] = speed
                self.youtube_downloads[download_id]["eta"] = eta

        self.youtube_speed.emit(download_id, speed, eta)

    def _on_youtube_finished(self, download_id: str, success: bool, message: str):
        """Handle YouTube download completion"""
        print(f"🎬 [Worker] YouTube download finished: {download_id} - Success: {success} - Message: {message}")

        if "cancelled" in message.lower() or "cancel" in message.lower():
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    del self.youtube_downloads[download_id]
                if download_id in self.youtube_workers:
                    del self.youtube_workers[download_id]
                self.youtube_gids.discard(download_id)
            print(f"🗑️ [Worker] YouTube download cancelled and cleaned up: {download_id}")
            return

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                if success:
                    self.youtube_downloads[download_id]["status"] = "completed"
                    self.youtube_downloads[download_id]["progress"] = 100
                    self.store.update_youtube_status(download_id, "completed")
                else:
                    self.youtube_downloads[download_id]["status"] = "error"
                    self.youtube_downloads[download_id]["error_message"] = message
                    self.store.update_youtube_status(download_id, "error")

            if download_id in self.youtube_workers:
                del self.youtube_workers[download_id]

            self.youtube_gids.discard(download_id)

        self.youtube_finished.emit(download_id, success, message)

    def _stop_all_youtube_downloads(self):
        """Stop all YouTube downloads"""
        with self.youtube_lock:
            for download_id, worker in list(self.youtube_workers.items()):
                if worker.is_running():
                    worker.cancel()
                    if download_id in self.youtube_downloads:
                        self.youtube_downloads[download_id]["status"] = "paused"
                        self.store.update_youtube_status(download_id, "paused")
            self.youtube_workers.clear()
            print("🛑 All YouTube downloads stopped")

    def _fetch_size_for_gid(self, gid: str, url: str):
        """دریافت حجم و کتگوری برای یک دانلود مشخص (فقط برای aria2)"""
        if gid in self.youtube_gids:
            return

        if gid in self._fetched_sizes:
            return

        try:
            from core.file_size_fetcher import get_file_size
            from utils.helpers import get_category_from_filename

            size = get_file_size(url, timeout=10)
            
            if size is not None and size < 0:
                size = size & 0xFFFFFFFF
                print(f"🔄 [Size] Converted negative to unsigned: {size}")
            
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
                print(f"✅ [BackendWorker] Size fetched for {gid}: {size} bytes ({size/1024/1024/1024:.2f} GB)")
            else:
                print(f"⚠️⚠️⚠️ [BackendWorker] Could not fetch size for {gid}")

        except Exception as e:
            import traceback
            traceback.print_exc()
        finally:
            self._fetching_sizes.discard(gid)