"""Video (yt-dlp) downloads: add, start, pause, resume, cancel, progress dialogs."""

import os
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from ui.dialogs import VideoDownloadDialog
from utils.helpers import is_known_video_site
from ui.video_progress import VideoProgressDialog


class VideoMixin:
    """Video (yt-dlp) downloads: add, start, pause, resume, cancel, progress dialogs."""

    def _cancel_video_workers_for(
        self, gids: List[str], delete_files: bool = False
    ) -> None:
        """Stop the yt-dlp worker behind any Video download in `gids`.

        aria2 removal does nothing for Video items (there is no aria2 gid),
        so without this the subprocess keeps running in the background.
        `delete_files` decides whether the worker also removes what it
        produced.
        """
        if not hasattr(self, "worker") or not self.worker:
            return

        for gid in gids:
            data = self._all_downloads.get(gid)
            if data is None:
                # Fall back to the persisted record: a queued Video item
                # may not be in the runtime dict yet.
                try:
                    if self.store.get_video_download(gid):
                        data = {"download_type": "video"}
                except Exception:
                    data = None
            if data is None or data.get("download_type") != "video":
                continue

            # Suppress the stats-snapshot handler from resurrecting this
            # item while the worker is still winding down.
            self._cancelling_video.add(gid)

            if gid in self._video_dialogs:
                try:
                    self._video_dialogs[gid].close()
                except Exception:
                    pass
                self._video_dialogs.pop(gid, None)

            try:
                if delete_files:
                    self.worker.cancel_video_download(gid)
                else:
                    self.worker.cancel_video_download_without_delete(gid)
            except Exception as e:
                print(f"⚠️ [Remove] Could not cancel Video worker {gid[:12]}: {e}")

            # Drop the persisted Video record so it cannot come back after
            # a restart.
            try:
                self.store.delete_video_download(gid)
            except Exception as e:
                print(f"⚠️ [Remove] Could not delete Video record {gid[:12]}: {e}")

            # Keep the guard for a while: a stats snapshot taken before the
            # cancel can still arrive and would re-create the row as
            # "downloading" -- a ghost nothing ever updates, which keeps the
            # tray icon green forever.
            QTimer.singleShot(5000, lambda g=gid: self._cancelling_video.discard(g))

    def _open_video_dialog_with_url(self, url: str) -> None:
        """Open the download dialog for a media URL (Video or any yt-dlp site)."""
        existing = self._open_dialogs.get("video_download")
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.close()
            except RuntimeError:
                pass
            self._open_dialogs.pop("video_download", None)

        queues = [q for q in self.store.queues if q.name != "__direct__"]
        default_idx = 0
        current_q = self._current_queue()
        if current_q and current_q.name != "__direct__":
            for i, q in enumerate(queues):
                if q.name == current_q.name:
                    default_idx = i
                    break

        dlg = VideoDownloadDialog(
            parent=self, queues=queues, default_queue=default_idx
        )
        dlg.video_download_requested.connect(self._add_video_to_queue)
        dlg.video_playlist_requested.connect(self._add_video_playlist_to_queue)

        dlg.url_edit.setText(url)
        # Do NOT auto-fetch — user clicks "Get Info" manually.

        # Set a meaningful title based on the domain.
        try:
            from urllib.parse import urlparse

            host = urlparse(url).hostname or ""
        except Exception:
            host = ""
        if host:
            dlg.setWindowTitle(f"Video Download — {host}")
        else:
            dlg.setWindowTitle("Video Download")

        self._show_singleton_dialog("video_download", dlg)

    def _video_download(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        default_idx = 0
        current_q = self._current_queue()
        if current_q and current_q.name != "__direct__":
            for i, q in enumerate(queues):
                if q.name == current_q.name:
                    default_idx = i
                    break

        dlg = VideoDownloadDialog(
            parent=self, queues=queues, default_queue=default_idx
        )
        dlg.video_download_requested.connect(self._add_video_to_queue)
        dlg.video_playlist_requested.connect(self._add_video_playlist_to_queue)

        clip = QApplication.clipboard().text().strip()
        if clip and "\n" not in clip and is_known_video_site(clip):
            dlg.url_edit.setText(clip)

        self._show_singleton_dialog("video_download", dlg)

    def _add_video_playlist_to_queue(self, items: List[Dict[str, Any]]) -> None:
        """Add every selected playlist video as its own download."""
        if not items:
            return
        for item in items:
            self._add_video_to_queue(item, batch=True)

        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        queue_name = items[0].get("queue_id", "Default")
        self.tray.showMessage(
            "FelfelDM",
            f"Added {len(items)} playlist videos to '{queue_name}'",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _add_video_to_queue(
        self, download_data: Dict[str, Any], batch: bool = False
    ) -> None:
        """Add one video download. `batch=True` (playlists) skips the
        per-item progress dialog, refresh and notification."""
        print("🎯 _add_video_to_queue CALLED")

        queue_name = download_data.get("queue_id", "Default")

        target_queue = self._get_or_create_queue(queue_name)

        download_id = str(uuid.uuid4())

        yt_options = download_data.get("yt_options", {})
        video_info = download_data.get("video_info", {})
        title = video_info.get("title", "Unknown Video")

        format_type = yt_options.get("format", "video")
        ext = "mp4" if format_type == "video" else "mp3"
        filename = re.sub(r'[<>:"/\\|?*]', "_", f"{title}.{ext}")
        full_path = os.path.join(download_data["save_path"], filename)

        video_data = {
            "id": download_id,
            "url": download_data["url"],
            "save_path": download_data["save_path"],
            "queue_id": queue_name,
            "download_type": "video",
            "status": "paused",
            "progress": 0,
            "speed": "",
            "eta": "",
            "yt_options": {
                "title": title,
                "quality": yt_options.get("quality", "best"),
                "format": format_type,
                "cookies_path": yt_options.get("cookies_path"),
                "format_id": yt_options.get("format_id"),
                "format_spec": yt_options.get("format_spec", "bv+ba/b"),
                "format_info": yt_options.get("format_info", {}),
            },
            "proxy": download_data.get("proxy"),
            "video_info": video_info,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "error_message": "",
            "filename": filename,
            "full_path": full_path,
        }

        self.store.add_video_download(video_data)

        self._all_downloads[download_id] = {
            "gid": download_id,
            "name": title,
            "status": "paused",
            "totalLength": 0,
            "completedLength": 0,
            "downloadSpeed": 0,
            "connections": 0,
            "files": [{"path": full_path}],
            "errorMessage": "",
            "category": "🎬 Video",
            "download_type": "video",
            "real_path": full_path,
            "save_path": download_data["save_path"],
            "yt_options": video_data["yt_options"],
        }

        if download_id not in target_queue.downloads:
            target_queue.downloads.append(download_id)

        target_queue.downloads_info[download_id] = {
            "url": download_data["url"],
            "name": title,
            "totalLength": 0,
            "completedLength": 0,
            "status": "paused",
            "category": "🎬 Video",
            "download_type": "video",
            "files": [{"path": full_path}],
            "real_path": full_path,
            "save_path": download_data["save_path"],
        }

        self.store.save()

        is_direct = queue_name == "__direct__"
        if is_direct:
            target_queue.paused = False
            self._all_downloads[download_id]["status"] = "downloading"
            target_queue.downloads_info[download_id]["status"] = "downloading"

            self.store.update_video_status(download_id, "downloading")

            self.store.save()

        if self.worker:
            self.worker.add_video_download(
                {
                    "id": download_id,
                    "url": download_data["url"],
                    "save_path": download_data["save_path"],
                    "yt_options": video_data["yt_options"],
                    "proxy": download_data.get("proxy"),
                    "queue_id": queue_name,
                }
            )

        if batch:
            return

        if is_direct:
            QTimer.singleShot(
                300, lambda did=download_id: self._open_video_progress_dialog(did)
            )

        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        self.tray.showMessage(
            "FelfelDM",
            f"Added video download to '{queue_name}': {title[:50]}...",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _start_video_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            print(f"⚠️ [MainWindow] No worker available")
            return

        data = self.store.get_video_download(download_id)
        if not data:
            print(f"⚠️ [MainWindow] No data for {download_id}")
            return

        worker_exists = False
        try:
            with self.worker.video_lock:
                worker_exists = download_id in self.worker.video_workers
        except Exception:
            worker_exists = False

        if worker_exists:
            print(f"⏭️ [MainWindow] Worker already exists for {download_id}")
            return

        print(f"🎬 [MainWindow] Starting Video download: {download_id}")
        self.worker.add_video_download(
            {
                "id": download_id,
                "url": data["url"],
                "save_path": data["save_path"],
                "yt_options": data.get("yt_options", {}),
                "proxy": data.get("proxy"),
                "queue_id": data.get("queue_id"),
                # Explicit intent: this is a start request, so the worker
                # must not inherit a stale "paused" status from the store.
                "status": "downloading",
            }
        )

    def _pause_video_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            return

        self.worker.pause_video_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "paused"

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["status"] = "paused"
                break

        self.store.save()
        self._update_queue_buttons()
        self._refresh_table()

    def _resume_video_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            return

        worker_exists = False
        try:
            with self.worker.video_lock:
                worker_exists = download_id in self.worker.video_workers
        except Exception:
            worker_exists = False

        if worker_exists:
            print(f"▶️ [MainWindow] Resuming existing worker: {download_id}")
            self.worker.resume_video_download(download_id)
        else:
            print(f"🎬 [MainWindow] No active worker, starting fresh: {download_id}")
            data = self.store.get_video_download(download_id)
            if not data:
                print(f"⚠️ [MainWindow] No data for {download_id}")
                return
            self.worker.add_video_download(
                {
                    "id": download_id,
                    "url": data["url"],
                    "save_path": data["save_path"],
                    "yt_options": data.get("yt_options", {}),
                    "proxy": data.get("proxy"),
                    "queue_id": data.get("queue_id"),
                    # Resume is also an explicit "run now" request.
                    "status": "downloading",
                }
            )

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["status"] = "downloading"
                break

        self.store.save()
        self._update_queue_buttons()
        self._refresh_table()

    def _cancel_video_download(self, download_id: str) -> None:
        print(f"🗑️ [MainWindow] _cancel_video_download CALLED for: {download_id}")
        self._cancelling_video.add(download_id)
        print(
            f"🗑️ [MainWindow] _all_downloads count BEFORE: {len(self._all_downloads)}"
        )

        if not hasattr(self, "worker"):
            print(f"⚠️ [MainWindow] No worker")
            return

        print(f"🗑️ [MainWindow] Updating UI first...")

        if download_id in self._video_dialogs:
            try:
                self._video_dialogs[download_id].close()
            except Exception:
                pass
            self._video_dialogs.pop(download_id, None)

        self.store.delete_video_download(download_id)
        self.store.save()

        if download_id in self._all_downloads:
            del self._all_downloads[download_id]

        for q in self.store.queues:
            if download_id in q.downloads:
                q.downloads.remove(download_id)
            if download_id in q.downloads_info:
                del q.downloads_info[download_id]
        self.store.save()

        print(f"🗑️ [MainWindow] Calling worker.cancel_video_download...")
        try:
            self.worker.cancel_video_download(download_id)
        except Exception as e:
            print(f"⚠️ [MainWindow] Error in worker.cancel_video_download: {e}")

        self._reset_speed_if_idle()

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

        print(f"🗑️ [MainWindow] _all_downloads count AFTER: {len(self._all_downloads)}")
        print(f"🗑️ [MainWindow] Cancel complete for: {download_id}")
        QTimer.singleShot(
            5000, lambda did=download_id: self._cancelling_video.discard(did)
        )

    def _on_video_progress(self, download_id: str, progress: int) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["progress"] = progress
            self._all_downloads[download_id]["status"] = "downloading"
            self._refresh_table()

    def _on_video_status(self, download_id: str, status: str) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = status
            self._update_queue_buttons()
            self._refresh_table()

    def _on_video_speed(self, download_id: str, speed: str, eta: str) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["speed"] = speed
            self._all_downloads[download_id]["eta"] = eta
            self._all_downloads[download_id]["downloadSpeed"] = self._parse_speed(speed)
            self._refresh_table()

    def _on_video_size_fetched(self, download_id: str, size: int) -> None:
        if size <= 0:
            self._size_unknown.add(download_id)
        else:
            self._size_unknown.discard(download_id)
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["totalLength"] = max(size, 0)
            self._refresh_table()

    def _on_video_finished(
        self, download_id: str, success: bool, message: str
    ) -> None:
        print(f"🎬 [MainWindow] Video finished: {download_id} success={success}")

        if download_id in self._video_dialogs:
            dialog = self._video_dialogs[download_id]
            try:
                dialog.update_finished(success, message)
            except RuntimeError:
                self._video_dialogs.pop(download_id, None)

        if success:
            self.tray.showMessage(
                "FelfelDM",
                "Video download completed!",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        elif "cancelled" not in message.lower():
            self.tray.showMessage(
                "FelfelDM",
                f"❌ Video download failed: {message}",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )

        self._refresh_table()

    def _open_video_progress_dialog(self, download_id: str) -> None:
        try:
            if not download_id:
                return

            if download_id in self._video_dialogs:
                dialog = self._video_dialogs[download_id]
                try:
                    if dialog.isVisible():
                        dialog.raise_()
                        dialog.activateWindow()
                        return
                    else:
                        dialog.deleteLater()
                        del self._video_dialogs[download_id]
                except RuntimeError:
                    del self._video_dialogs[download_id]

            data = self.store.get_video_download(download_id)
            if not data:
                QMessageBox.warning(self, "Error", "Download not found")
                return

            dialog = VideoProgressDialog(
                url=data["url"],
                output_path=data["save_path"],
                format_type=data.get("yt_options", {}).get("format", "mp4"),
                cookie_file=data.get("yt_options", {}).get("cookies_path"),
                video_info=data.get("video_info", {}),
                parent=None,
                proxy_url=data.get("proxy"),
                download_id=download_id,
            )

            dialog.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowMinimizeButtonHint
            )
            dialog.setWindowModality(Qt.WindowModality.NonModal)

            dialog.pause_requested.connect(self._pause_video_download)
            dialog.resume_requested.connect(self._resume_video_download)
            dialog.cancel_requested.connect(self._cancel_video_download)

            dialog.finished.connect(
                lambda result, did=download_id: self._on_video_dialog_closed(
                    did, result
                )
            )

            self._video_dialogs[download_id] = dialog
            dialog.show()
            self._center_dialog_on_screen(dialog)

            video_title = (
                data.get("yt_options", {}).get("title") or data.get("name") or ""
            )
            if video_title:
                dialog.setWindowTitle(video_title)

            if download_id in self._all_downloads:
                dl_data = self._all_downloads[download_id]
                status = dl_data.get("status", "pending")
                progress = dl_data.get("progress", 0)
                speed = dl_data.get("speed", "")
                eta = dl_data.get("eta", "")

                dialog.update_progress(progress, speed, eta)

                if status == "paused":
                    dialog.update_pause_state(True)
                elif status == "downloading":
                    dialog.update_pause_state(False)
                elif status == "completed":
                    dialog.update_finished(True, "Download completed!")

        except Exception as e:
            print(f"❌ Error opening Video dialog: {e}")

    def _on_video_dialog_closed(self, download_id: str, result=None) -> None:
        if download_id in self._video_dialogs:
            dialog = self._video_dialogs.pop(download_id)
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _update_video_dialogs(self, video_downloads: List[Dict]) -> None:
        for yt_data in video_downloads:
            if not isinstance(yt_data, dict):
                continue

            yt_id = yt_data.get("id")
            if not yt_id:
                continue

            if yt_id in self._cancelling_video:
                print(f"⏭️ [MainWindow] Skipping cancelling download: {yt_id[:8]}")
                continue

            # Never resurrect a row that is neither in the UI nor in a queue.
            if yt_id not in self._all_downloads and not any(
                yt_id in q.downloads for q in self.store.queues
            ):
                continue

            saved_data = self.store.get_video_download(yt_id)
            status = yt_data.get("status", "pending")
            progress = yt_data.get("progress", 0)
            speed = yt_data.get("speed", "")
            eta = yt_data.get("eta", "")
            total_size = yt_data.get("total_size", 0)
            title = yt_data.get("title", "Unknown")

            if saved_data:
                title = saved_data.get("yt_options", {}).get("title", title)

            completed = int(total_size * progress / 100) if total_size > 0 else 0

            if yt_id in self._all_downloads:
                self._all_downloads[yt_id].update(
                    {
                        "name": title,
                        "status": status,
                        "progress": progress,
                        "speed": speed,
                        "eta": eta,
                        "totalLength": total_size,
                        "completedLength": completed,
                        "downloadSpeed": self._parse_speed(speed),
                        "download_type": "video",
                        "category": "🎬 Video",
                    }
                )
            else:
                self._all_downloads[yt_id] = {
                    "gid": yt_id,
                    "name": title,
                    "status": status,
                    "progress": progress,
                    "speed": speed,
                    "eta": eta,
                    "totalLength": total_size,
                    "completedLength": completed,
                    "downloadSpeed": self._parse_speed(speed),
                    "connections": 0,
                    "files": [],
                    "errorMessage": "",
                    "category": "🎬 Video",
                    "download_type": "video",
                }

            if saved_data and saved_data.get("status") != status:
                self.store.update_video_status(yt_id, status)

            self._update_open_video_dialog(
                yt_id, status, progress, speed, eta, total_size
            )

        # Self-heal: a Video row that still claims to be active although
        # the worker no longer knows it can never finish, and it would keep
        # the tray icon green. Mark it paused so the user can resume/remove.
        reported = {d.get("id") for d in video_downloads if isinstance(d, dict)}
        for did, info in self._all_downloads.items():
            if (
                info.get("download_type") == "video"
                and info.get("status") in ("active", "downloading")
                and did not in reported
                and did not in self._cancelling_video
            ):
                info["status"] = "paused"
                info["speed"] = ""
                info["downloadSpeed"] = 0

    def _update_open_video_dialog(
        self,
        download_id: str,
        status: str,
        progress: int,
        speed: str,
        eta: str,
        total_size: int,
    ) -> None:
        if download_id not in self._video_dialogs:
            return

        dialog = self._video_dialogs[download_id]

        try:
            dialog.update_progress(progress, speed, eta)

            if status == "paused":
                dialog.update_pause_state(True)
            elif status in ("downloading", "active"):
                dialog.update_pause_state(False)

            if status in ("completed", "complete"):
                dialog.update_finished(True, "Download completed successfully!")
            elif status == "error":
                msg = self._all_downloads.get(download_id, {}).get(
                    "errorMessage", "Download failed"
                )
                dialog.update_finished(False, msg)
        except RuntimeError:
            self._video_dialogs.pop(download_id, None)
