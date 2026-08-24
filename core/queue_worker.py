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

        youtube_gids = []
        normal_gids = []
        for gid in q.downloads:
            download_type = self._all_downloads.get(gid, {}).get(
                "download_type", "normal"
            )
            if download_type == "youtube":
                youtube_gids.append(gid)
            else:
                normal_gids.append(gid)

        resumed_count = 0

        # ===== YouTube =====
        for gid in youtube_gids:
            real_status = self._all_downloads.get(gid, {}).get("status", "")
            if real_status == "paused":
                self.worker.resume_youtube_download(gid)
                self.download_status_changed.emit(gid, "downloading")
                resumed_count += 1
                self.status_update.emit(f"Resuming YouTube: {gid[:8]}...")

        # ===== Normal =====
        if normal_gids:
            self.status_update.emit(f"Checking status of {len(normal_gids)} item(s)...")
            try:
                statuses = self.aria2.get_status_multi(normal_gids)
            except Exception as e:
                statuses = {}
                self.status_update.emit(f"❌ Status check failed: {str(e)[:30]}")

            to_resume = []
            for gid in normal_gids:
                status_data = statuses.get(gid)
                if not status_data:
                    self.status_update.emit(f"⏭️ Skipping (not in aria2): {gid[:8]}...")
                    continue

                real_status = status_data.get("status", "unknown")

                if real_status in ["paused", "waiting"]:
                    to_resume.append(gid)
                    self.download_status_changed.emit(gid, "active")
                    resumed_count += 1
                elif real_status == "active":
                    self.download_status_changed.emit(gid, "active")
                    resumed_count += 1
                else:
                    self.status_update.emit(
                        f"Unknown status {real_status}: {gid[:8]}..."
                    )

            if to_resume:
                for i, gid in enumerate(to_resume):
                    try:
                        self.aria2._call("aria2.changePosition", [gid, i, "POS_SET"])
                    except Exception as e:
                        print(f"⚠️ changePosition failed for {gid}: {e}")
                self.status_update.emit(f"Resuming {len(to_resume)} item(s)...")
                self.worker.resume_multi_requested.emit(to_resume)

            if q and getattr(q, "speed_limit", 0) > 0:
                try:
                    self.worker.set_speed_limit_multi_requested.emit(
                        normal_gids, q.speed_limit
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

        for idx, gid in enumerate(q.downloads):
            self.progress.emit(idx + 1, total)

            download_type = self._all_downloads.get(gid, {}).get(
                "download_type", "normal"
            )

            if download_type == "youtube":
                real_status = self._all_downloads.get(gid, {}).get("status", "")
                if real_status in ["downloading", "pending"]:
                    self.worker.pause_youtube_download(gid)
                    self.download_status_changed.emit(gid, "paused")
                    paused_count += 1
                    self.status_update.emit(f"Pausing YouTube: {gid[:8]}...")
            else:
                try:
                    status_data = self.aria2.get_status(gid)
                    if not status_data:
                        self.status_update.emit(
                            f"⚠️ Cannot pause: GID not found {gid[:8]}..."
                        )
                        continue

                    real_status = status_data.get("status", "unknown")

                    if real_status in ["active", "waiting"]:
                        self.worker.pause_requested.emit(gid)
                        self.download_status_changed.emit(gid, "paused")
                        paused_count += 1
                        self.status_update.emit(f"Pausing: {gid[:8]}...")
                    elif real_status == "paused":
                        self.status_update.emit(f"Already paused: {gid[:8]}...")
                    else:
                        self.status_update.emit(f"Status {real_status}: {gid[:8]}...")

                except Exception as e:
                    self.status_update.emit(f"❌ Error on {gid[:8]}: {str(e)[:30]}")
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
