# core/worker.py

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from typing import Dict, Optional, List, Set, Any
import threading
import uuid
from datetime import datetime
import os
import time
import re
import glob

from core.youtube_worker import YouTubeWorker
from core.data_store import DataStore


class BackendWorker(QThread):

    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)
    size_fetched = pyqtSignal(str, object, str)

    resume_requested = pyqtSignal(str)
    pause_requested = pyqtSignal(str)
    remove_requested = pyqtSignal(str)
    add_url_requested = pyqtSignal(str, dict)
    re_add_requested = pyqtSignal(str)
    set_speed_limit_requested = pyqtSignal(str, int)
    save_session_requested = pyqtSignal()
    shutdown_requested = pyqtSignal()

    operation_result = pyqtSignal(str, object)

    youtube_progress = pyqtSignal(str, int)
    youtube_status = pyqtSignal(str, str)
    youtube_speed = pyqtSignal(str, str, str)
    youtube_finished = pyqtSignal(str, bool, str)
    youtube_size_fetched = pyqtSignal(str, int)

    def __init__(self, aria2, store: DataStore):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.running = True

        self._fetching_sizes: Set[str] = set()
        self._fetched_sizes: Set[str] = set()

        self.youtube_workers: Dict[str, YouTubeWorker] = {}
        self.youtube_downloads: Dict[str, dict] = {}
        self.youtube_lock = threading.Lock()
        self.youtube_gids: Set[str] = set()
        self._size_workers: Dict[str, YouTubeWorker] = {}

        self._download_cache: Dict[str, dict] = {}
        self._last_update_time: Dict[str, float] = {}
        self._CACHE_TTL = 0.1

        self.resume_requested.connect(
            self._on_resume_requested, Qt.ConnectionType.QueuedConnection
        )
        self.pause_requested.connect(
            self._on_pause_requested, Qt.ConnectionType.QueuedConnection
        )
        self.remove_requested.connect(
            self._on_remove_requested, Qt.ConnectionType.QueuedConnection
        )
        self.add_url_requested.connect(
            self._on_add_url_requested, Qt.ConnectionType.QueuedConnection
        )
        self.re_add_requested.connect(
            self._on_re_add_requested, Qt.ConnectionType.QueuedConnection
        )
        self.set_speed_limit_requested.connect(
            self._on_set_speed_limit, Qt.ConnectionType.QueuedConnection
        )
        self.save_session_requested.connect(
            self._on_save_session, Qt.ConnectionType.QueuedConnection
        )
        self.shutdown_requested.connect(
            self._on_shutdown, Qt.ConnectionType.QueuedConnection
        )

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
                    print(
                        f"📁 Loading YouTube download: {download_id} - status: {status}"
                    )

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

    def run(self):
        """Main polling loop - builds complete runtime snapshot of all downloads"""
        while self.running:
            try:
                if not self.aria2.is_connected():
                    if not self.aria2.start_aria2():
                        self.stats_updated.emit({"connected": False})
                        self.msleep(100)
                        continue

                snapshot = self._build_runtime_snapshot()
                self.stats_updated.emit(snapshot)

            except Exception as e:
                self.aria2_error.emit(str(e))
                self.stats_updated.emit({"connected": False})

            self.msleep(100)

    def stop(self):
        self.running = False
        self._stop_all_youtube_downloads()
        self._stop_all_size_workers()
        if not self.wait(2000):
            self.terminate()

    def _build_runtime_snapshot(self) -> dict:
        active = self.aria2.tell_active() or []
        waiting = self.aria2.tell_waiting() or []
        stopped = self.aria2.tell_stopped(0, 300) or []

        all_downloads = active + waiting + stopped
        downloads_snapshot = []
        seen_gids = set()

        for download in all_downloads:
            gid = download.get("gid")
            if not gid or gid in seen_gids:
                continue
            seen_gids.add(gid)
            complete_info = self._get_complete_download_info(gid, download)
            if complete_info:
                downloads_snapshot.append(complete_info)

        try:
            youtube_status = self._get_youtube_status()
            if not isinstance(youtube_status, list):
                youtube_status = []
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            youtube_status = []

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

    def _get_complete_download_info(
        self, gid: str, partial_info: dict
    ) -> Optional[dict]:
        current_time = time.time()
        if (
            gid in self._download_cache
            and (current_time - self._last_update_time.get(gid, 0)) < self._CACHE_TTL
        ):
            cached = self._download_cache[gid].copy()
            if partial_info.get("status") != cached.get("status"):
                cached["status"] = partial_info.get("status")
            return cached

        try:
            full_info = self.aria2.tell_status(gid) or partial_info
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
            optional_fields = [
                "uploadLength",
                "uploadSpeed",
                "bitfield",
                "bittorrent",
                "verifiedLength",
                "verifyIntegrityPending",
                "seeder",
                "numSeeders",
                "pieceLength",
                "totalPieces",
                "dir",
                "infoHash",
                "numPieces",
            ]
            for field in optional_fields:
                if field in full_info:
                    complete_info[field] = full_info[field]

            self._download_cache[gid] = complete_info
            self._last_update_time[gid] = time.time()

            if complete_info.get("totalLength") == "0" and complete_info.get(
                "status"
            ) in ("active", "waiting", "paused"):
                if (
                    gid not in self.youtube_gids
                    and gid not in self._fetching_sizes
                    and gid not in self._fetched_sizes
                ):
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
        status_list = []
        try:
            with self.youtube_lock:
                for download_id, info in self.youtube_downloads.items():
                    status_list.append(
                        {
                            "id": download_id,
                            "url": info.get("url", ""),
                            "title": info.get("yt_options", {}).get("title", ""),
                            "status": info.get("status", "pending"),
                            "progress": info.get("progress", 0),
                            "speed": info.get("speed", ""),
                            "eta": info.get("eta", ""),
                            "total_size": info.get("total_size", 0),
                        }
                    )
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            return []
        return status_list

    def _fetch_size_for_gid(self, gid: str, url: str):

        if gid in self._fetched_sizes:
            print(f"⏭️ [Worker] Size already fetched for {gid}, skipping")
            return

        for q in self.store.queues:
            if gid in q.downloads_info:
                existing_size = q.downloads_info[gid].get("totalLength", 0)
                if existing_size > 0:
                    self._fetched_sizes.add(gid)
                    print(
                        f"⏭️ [Worker] Size exists in storage for {gid}: {existing_size}, skipping fetch"
                    )

                    from utils.helpers import get_category_from_filename

                    filename = None
                    for q2 in self.store.queues:
                        if gid in q2.downloads_info:
                            filename = q2.downloads_info[gid].get("name", "")
                            break
                    if not filename:
                        filename = url.split("/")[-1].split("?")[0]
                    category = get_category_from_filename(filename)
                    self.size_fetched.emit(gid, existing_size, category)

                    self._fetching_sizes.discard(gid)
                    return

        if gid in self.youtube_gids or gid in self._fetched_sizes:
            return

        try:
            from core.file_size_fetcher import get_file_size
            from utils.helpers import get_category_from_filename

            print(f"📏 [Worker] Fetching size for {gid}: {url[:50]}...")

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
                print(
                    f"✅ [BackendWorker] Size fetched for {gid}: {size} bytes ({size/1024/1024/1024:.2f} GB)"
                )
            else:
                print(f"⚠️⚠️⚠️ [BackendWorker] Could not fetch size for {gid}")
        except Exception as e:
            import traceback

            traceback.print_exc()
        finally:
            self._fetching_sizes.discard(gid)

    @pyqtSlot(str)
    def _on_resume_requested(self, gid: str):
        try:
            self.aria2.resume(gid)
            print(f"▶️ [Worker] Resumed {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Resume failed for {gid}: {e}")

    @pyqtSlot(str)
    def _on_pause_requested(self, gid: str):
        try:
            self.aria2.pause(gid)
            print(f"⏸️ [Worker] Paused {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Pause failed for {gid}: {e}")

    @pyqtSlot(str)
    def _on_remove_requested(self, gid: str):
        try:
            self.aria2.remove(gid)
            print(f"🗑️ [Worker] Removed {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Remove failed for {gid}: {e}")

    @pyqtSlot(str, dict)
    def _on_add_url_requested(self, url: str, options: dict):
        try:
            new_gid = self.aria2.add_url(url, options)
            self.operation_result.emit("add_url", new_gid)
            print(f"➕ [Worker] Added URL: {url} -> {new_gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Add URL failed: {e}")
            self.operation_result.emit("add_url", None)

    @pyqtSlot(str)
    def _on_re_add_requested(self, old_gid: str):
        try:
            url = None
            save_path = None
            speed_limit = 0
            for q in self.store.queues:
                if old_gid in q.downloads_info:
                    info = q.downloads_info[old_gid]
                    url = info.get("url")
                    save_path = q.save_path
                    speed_limit = getattr(q, "speed_limit", 0)
                    break

            if not url or not save_path:
                print(f"❌ [Worker] Cannot re-add: missing info for {old_gid}")
                self.operation_result.emit("re_add", None)
                return

            options = {
                "dir": save_path,
                "split": "8",
                "max-connection-per-server": "8",
                "continue": "true",
                "always-resume": "true",
            }
            if speed_limit > 0:
                options["max-download-limit"] = f"{speed_limit}K"

            new_gid = self.aria2.add_url(url, options)
            if new_gid:
                self.aria2.resume(new_gid)
                print(f"🔄 [Worker] Re-added {old_gid} -> {new_gid}")
                self.operation_result.emit("re_add", new_gid)
            else:
                self.operation_result.emit("re_add", None)
        except Exception as e:
            print(f"⚠️ [Worker] Re-add failed: {e}")
            self.operation_result.emit("re_add", None)

    @pyqtSlot(str, int)
    def _on_set_speed_limit(self, gid: str, speed_kb: int):
        try:
            limit = "0" if speed_kb <= 0 else f"{speed_kb}K"
            self.aria2.change_option(gid, {"max-download-limit": limit})
            print(f"⚡ [Worker] Speed limit set for {gid}: {limit}")
        except Exception as e:
            print(f"⚠️ [Worker] Set speed limit failed: {e}")

    @pyqtSlot()
    def _on_save_session(self):
        try:
            self.aria2.save_session()
            print(f"💾 [Worker] Session saved")
        except Exception as e:
            print(f"⚠️ [Worker] Save session failed: {e}")

    @pyqtSlot()
    def _on_shutdown(self):
        try:
            self.aria2.shutdown()
            print(f"🛑 [Worker] aria2 shutdown")
        except Exception as e:
            print(f"⚠️ [Worker] Shutdown failed: {e}")

    def add_youtube_download(self, download_data: dict) -> str:
        print(f"🔥🔥🔥 add_youtube_download CALLED")
        download_id = download_data.get("id") or str(uuid.uuid4())
        existing = self.store.get_youtube_download(download_id)
        if existing:
            print(f"📦 [ADD] Download already exists: {download_id}")
            with self.youtube_lock:
                self.youtube_downloads[download_id] = existing
                self.youtube_gids.add(download_id)
                total_size = existing.get("total_size", 0)
            if total_size > 0:
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
        print(f"📏📏📏 _fetch_youtube_size CALLED for {download_id}")
        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                return
            item = self.youtube_downloads[download_id]
            if item.get("total_size", 0) > 0:
                return
            url = item["url"]
            save_path = item["save_path"]
            format_type = item.get("yt_options", {}).get("format", "mp4")
            cookie_file = item.get("yt_options", {}).get("cookies_path")
            proxy_url = item.get("proxy")

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
        print(f"📏 [SIZE] Received size for {download_id}: {size} bytes")
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["total_size"] = size
                self.youtube_downloads[download_id]["status"] = "paused"
                self.store.update_youtube_download(
                    download_id,
                    {"total_size": size, "status": "paused"},
                )
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

    def _start_youtube_download(self, download_id: str):
        print(f"🎬🎬🎬 _start_youtube_download CALLED for: {download_id}")
        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                return
            item = self.youtube_downloads[download_id]
            total_size = item.get("total_size", 0)
            if total_size == 0:
                pass
            else:
                if item.get("status") in ["downloading", "completed"]:
                    return
                url = item["url"]
                save_path = item["save_path"]
                format_type = item.get("yt_options", {}).get("format", "mp4")
                cookie_file = item.get("yt_options", {}).get("cookies_path")
                proxy_url = item.get("proxy")

        if total_size == 0:
            self._fetch_youtube_size(download_id)
            return

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
        worker.start()
        print(f"🎬 YouTube download started: {download_id}")

    def _resume_youtube_download(self, item: dict):
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

    def resume_youtube_download(self, download_id: str):
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

    def cancel_youtube_download(self, download_id: str):
        print(f"🗑️ [Worker] Cancelling YouTube download: {download_id}")
        worker = None
        file_path = None
        save_path = None
        title = "Unknown"
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                del self.youtube_workers[download_id]
            if download_id in self.youtube_downloads:
                yt_options = self.youtube_downloads[download_id].get("yt_options", {})
                title = yt_options.get("title", "Unknown")
                format_type = yt_options.get("format", "video")
                ext = "mp4" if format_type == "video" else "mp3"
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

        print(
            f"🗑️ [Worker] YouTube download cancelled and files deleted: {download_id}"
        )

    def _delete_youtube_files(self, file_path: str, save_path: str, title: str):
        try:
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
                for f in glob.glob(os.path.join(save_path, pattern)):
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
                for f in glob.glob(os.path.join(save_path, pattern)):
                    try:
                        os.remove(f)
                        print(f"🗑️ Deleted partial (title): {f}")
                    except:
                        pass
        except Exception as e:
            print(f"⚠️ Error deleting files: {e}")

    def cancel_youtube_download_without_delete(self, download_id: str):
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

    def _on_youtube_progress(self, download_id: str, progress: int):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["progress"] = progress
                self.store.update_youtube_progress(download_id, progress)
        self.youtube_progress.emit(download_id, progress)

    def _on_youtube_status(self, download_id: str, status: str):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["status_text"] = status
        self.youtube_status.emit(download_id, status)

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["speed"] = speed
                self.youtube_downloads[download_id]["eta"] = eta
        self.youtube_speed.emit(download_id, speed, eta)

    def _on_youtube_finished(self, download_id: str, success: bool, message: str):
        print(
            f"🎬 [Worker] YouTube download finished: {download_id} - Success: {success} - Message: {message}"
        )
        if "cancelled" in message.lower() or "cancel" in message.lower():
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    del self.youtube_downloads[download_id]
                if download_id in self.youtube_workers:
                    del self.youtube_workers[download_id]
                self.youtube_gids.discard(download_id)
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
        with self.youtube_lock:
            for download_id, worker in list(self.youtube_workers.items()):
                if worker.is_running():
                    worker.cancel()
                    if download_id in self.youtube_downloads:
                        self.youtube_downloads[download_id]["status"] = "paused"
                        self.store.update_youtube_status(download_id, "paused")
            self.youtube_workers.clear()

    def _stop_all_size_workers(self):
        for download_id, worker in list(self._size_workers.items()):
            try:
                if worker.isRunning():
                    worker.quit()
                    worker.wait(1000)
            except:
                pass
        self._size_workers.clear()
