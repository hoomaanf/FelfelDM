# core/queue_worker.py

from PyQt6.QtCore import QThread, pyqtSignal
import time


class QueueOperationWorker(QThread):

    progress = pyqtSignal(int, int)
    status_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    download_status_changed = pyqtSignal(str, str)

    def __init__(self, queue, operation: str, main_window):
        super().__init__()
        self.queue = queue
        self.operation = operation
        self.main_window = main_window
        self.aria2 = main_window.aria2
        self.worker = main_window.worker
        self._all_downloads = main_window._all_downloads

    def _get_aria2_gid(self, download_id: str) -> str:
        """دریافت aria2_gid از download_id (UUID)."""
        data = self._all_downloads.get(download_id)
        if not data:
            return None
        return data.get("aria2_gid")

    def run(self):
        try:
            if self.operation == "start":
                self._start_queue()
            elif self.operation == "pause":
                self._pause_queue()
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.finished.emit(False, str(e))

    def _start_queue(self):
        q = self.queue
        total = len(q.downloads)

        if total == 0:
            self.finished.emit(True, "Queue is empty")
            return

        self.status_update.emit(f"Starting {total} download(s)...")

        youtube_ids = []
        normal_ids = []  # download_id (UUID)

        for download_id in q.downloads:
            download_type = self._all_downloads.get(download_id, {}).get(
                "download_type", "normal"
            )
            if download_type == "youtube":
                youtube_ids.append(download_id)
            else:
                normal_ids.append(download_id)

        resumed_count = 0

        # ===== YouTube =====
        for download_id in youtube_ids:
            real_status = self._all_downloads.get(download_id, {}).get("status", "")
            if real_status == "paused":
                self.worker.resume_youtube_download(download_id)
                self.download_status_changed.emit(download_id, "downloading")
                resumed_count += 1
                self.status_update.emit(f"Resuming YouTube: {download_id[:8]}...")

        # ===== Normal =====
        if normal_ids:
            self.status_update.emit(f"Checking status of {len(normal_ids)} item(s)...")

            # ⭐ UUID → aria2_gid map
            id_to_gid = {}
            for download_id in normal_ids:
                aria2_gid = self._get_aria2_gid(download_id)
                if aria2_gid:
                    id_to_gid[download_id] = aria2_gid

            if not id_to_gid:
                self.status_update.emit("⚠️ No aria2 GIDs found")
                self.finished.emit(True, "ℹ️ No downloads to resume")
                return

            # ⭐ درخواست status با GID های واقعی
            aria2_gids = list(id_to_gid.values())
            try:
                statuses = self.aria2.get_status_multi(aria2_gids)
            except Exception as e:
                statuses = {}
                self.status_update.emit(f"❌ Status check failed: {str(e)[:30]}")

            to_resume_gids = []  # aria2_gid
            for download_id, aria2_gid in id_to_gid.items():
                status_data = statuses.get(aria2_gid)
                if not status_data:
                    self.status_update.emit(
                        f"⏭️ Skipping (not in aria2): {download_id[:8]}..."
                    )
                    continue

                real_status = status_data.get("status", "unknown")

                if real_status in ["paused", "waiting"]:
                    to_resume_gids.append(aria2_gid)
                    self.download_status_changed.emit(download_id, "active")
                    resumed_count += 1
                elif real_status == "active":
                    self.download_status_changed.emit(download_id, "active")
                    resumed_count += 1
                else:
                    self.status_update.emit(
                        f"Unknown status {real_status}: {download_id[:8]}..."
                    )

            if to_resume_gids:
                for i, aria2_gid in enumerate(to_resume_gids):
                    try:
                        self.aria2._call(
                            "aria2.changePosition",
                            [aria2_gid, i, "POS_SET"],
                        )
                    except Exception as e:
                        print(f"⚠️ changePosition failed for {aria2_gid}: {e}")
                self.status_update.emit(f"Resuming {len(to_resume_gids)} item(s)...")
                self.worker.resume_multi_requested.emit(to_resume_gids)

            if q and getattr(q, "speed_limit", 0) > 0:
                try:
                    self.worker.set_speed_limit_multi_requested.emit(
                        aria2_gids, q.speed_limit
                    )
                except Exception:
                    pass

        try:
            self.main_window.store.save()
        except Exception:
            pass

        if resumed_count > 0:
            self.finished.emit(True, f"✅ Started {resumed_count} download(s)")
        else:
            self.finished.emit(True, "ℹ️ No downloads to resume")

    def _pause_queue(self):
        q = self.queue
        total = len(q.downloads)

        if total == 0:
            self.finished.emit(True, "Queue is empty")
            return

        self.status_update.emit(f"Pausing {total} download(s)...")

        paused_count = 0

        for idx, download_id in enumerate(q.downloads):
            self.progress.emit(idx + 1, total)

            download_type = self._all_downloads.get(download_id, {}).get(
                "download_type", "normal"
            )

            if download_type == "youtube":
                real_status = self._all_downloads.get(download_id, {}).get("status", "")
                if real_status in ["downloading", "pending"]:
                    self.worker.pause_youtube_download(download_id)
                    self.download_status_changed.emit(download_id, "paused")
                    paused_count += 1
                    self.status_update.emit(f"Pausing YouTube: {download_id[:8]}...")
            else:
                aria2_gid = self._get_aria2_gid(download_id)
                if not aria2_gid:
                    self.status_update.emit(
                        f"⚠️ No aria2_gid for: {download_id[:8]}..."
                    )
                    continue

                try:
                    status_data = self.aria2.get_status(aria2_gid)
                    if not status_data:
                        self.status_update.emit(
                            f"⚠️ Cannot pause: GID not found {aria2_gid[:8]}..."
                        )
                        continue

                    real_status = status_data.get("status", "unknown")

                    if real_status in ["active", "waiting"]:
                        self.worker.pause_requested.emit(aria2_gid)
                        self.download_status_changed.emit(download_id, "paused")
                        paused_count += 1
                        self.status_update.emit(f"Pausing: {download_id[:8]}...")
                    elif real_status == "paused":
                        self.status_update.emit(f"Already paused: {download_id[:8]}...")
                    else:
                        self.status_update.emit(
                            f"Status {real_status}: {download_id[:8]}..."
                        )

                except Exception as e:
                    self.status_update.emit(
                        f"❌ Error on {download_id[:8]}: {str(e)[:30]}"
                    )
                    continue

            if idx % 5 == 0:
                time.sleep(0.01)

        try:
            self.main_window.store.save()
        except Exception:
            pass

        if paused_count > 0:
            self.finished.emit(True, f"⏸️ Paused {paused_count} download(s)")
        else:
            self.finished.emit(True, "ℹ️ No active downloads to pause")
