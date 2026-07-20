# core/queue_worker.py

from PyQt6.QtCore import QThread, pyqtSignal, QTimer, QEventLoop
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

        resumed_count = 0
        error_count = 0

        for idx, gid in enumerate(q.downloads):
            self.progress.emit(idx + 1, total)

            download_type = self._all_downloads.get(gid, {}).get(
                "download_type", "normal"
            )

            if download_type == "youtube":

                real_status = self._all_downloads.get(gid, {}).get("status", "")
                if real_status == "paused":

                    self.worker.resume_youtube_download(gid)
                    self.download_status_changed.emit(gid, "downloading")
                    resumed_count += 1
                    self.status_update.emit(f"Resuming YouTube: {gid[:8]}...")
            else:

                try:
                    status_data = self.aria2.get_status(gid)

                    if not status_data:

                        self.status_update.emit(f"Re-adding: {gid[:8]}...")
                        self.worker.re_add_requested.emit(gid)
                        resumed_count += 1
                        continue

                    real_status = status_data.get("status", "unknown")

                    if real_status in ["paused", "waiting", "error"]:

                        self.worker.resume_requested.emit(gid)
                        self.download_status_changed.emit(gid, "active")
                        resumed_count += 1
                        self.status_update.emit(f"Resuming: {gid[:8]}...")

                    elif real_status == "active":
                        self.download_status_changed.emit(gid, "active")
                        resumed_count += 1
                        self.status_update.emit(f"Already active: {gid[:8]}...")

                    else:
                        self.status_update.emit(
                            f"Unknown status {real_status}: {gid[:8]}..."
                        )

                except Exception as e:
                    error_count += 1
                    self.status_update.emit(f"❌ Error on {gid[:8]}: {str(e)[:30]}")
                    continue

                if q and getattr(q, "speed_limit", 0) > 0:
                    try:
                        self.worker.set_speed_limit_requested.emit(gid, q.speed_limit)
                    except Exception:
                        pass

            if idx % 5 == 0:
                time.sleep(0.01)

        try:
            self.main_window.store.save()
        except Exception:
            pass

        if resumed_count > 0:
            self.finished.emit(True, f"✅ Started {resumed_count} download(s)")
        elif error_count > 0:
            self.finished.emit(
                True, f"⚠️ Started {resumed_count} download(s), {error_count} errors"
            )
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
        error_count = 0

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

                    if status_data:
                        real_status = status_data.get("status", "unknown")
                    else:
                        real_status = self._all_downloads.get(gid, {}).get(
                            "status", "unknown"
                        )

                    if real_status in ["active", "waiting"]:

                        self.worker.pause_requested.emit(gid)
                        self.download_status_changed.emit(gid, "paused")
                        paused_count += 1
                        self.status_update.emit(f"Pausing: {gid[:8]}...")

                    elif real_status == "paused":
                        self.status_update.emit(f"Already paused: {gid[:8]}...")

                except Exception as e:
                    error_count += 1
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
        elif error_count > 0:
            self.finished.emit(
                True, f"⚠️ Paused {paused_count} download(s), {error_count} errors"
            )
        else:
            self.finished.emit(True, "ℹ️ No active downloads to pause")


class RetryWorker(QThread):
    progress = pyqtSignal(str, int)
    status_update = pyqtSignal(str, str)
    finished = pyqtSignal(str, bool)

    def __init__(self, gid: str, main_window, max_retries: int = 5):
        super().__init__()
        self.gid = gid
        self.main_window = main_window
        self.max_retries = max_retries
        self.aria2 = main_window.aria2
        self.worker = main_window.worker
        self._all_downloads = main_window._all_downloads
        self._should_stop = False
        self._loop = QEventLoop()

        self.retry_delay = main_window.store.settings.get("retry_delay", 1.0)
        self.retry_delay_ms = int(self.retry_delay * 1000)

    def stop(self):
        self._should_stop = True
        if self._loop and self._loop.isRunning():
            self._loop.quit()

    def _wait(self, ms: int):
        if self._should_stop:
            return
        self._loop = QEventLoop()
        QTimer.singleShot(ms, self._loop.quit)
        self._loop.exec()

    def run(self):
        try:

            if self.gid not in self._all_downloads:
                self.finished.emit(self.gid, False)
                return

            data = self._all_downloads[self.gid]
            error_count = self.main_window._to_int(data.get("error_count", 0))

            error_count += 1
            data["error_count"] = error_count
            data["status"] = "retrying"

            self.progress.emit(self.gid, error_count)
            self.status_update.emit(
                self.gid, f"🔄 Retrying ({error_count}/{self.max_retries})..."
            )

            if self._should_stop:
                return

            if self.worker is not None:

                self.worker.resume_requested.emit(self.gid)

                self._wait(self.retry_delay_ms)

                if self._should_stop:
                    return

                status_data = self.aria2.get_status(self.gid)
                if status_data:
                    new_status = status_data.get("status", "")
                    if new_status in ["active", "waiting"]:
                        data["status"] = "active"
                        data["error_count"] = 0
                        self.status_update.emit(self.gid, "✅ Resumed")
                        self.finished.emit(self.gid, True)
                        return

                self.status_update.emit(self.gid, "🔄 Re-adding...")
                self.worker.re_add_requested.emit(self.gid)

                self._wait(1000)

                if self._should_stop:
                    return

                status_data = self.aria2.get_status(self.gid)
                if status_data:
                    new_status = status_data.get("status", "")
                    if new_status in ["active", "waiting"]:
                        data["status"] = "active"
                        data["error_count"] = 0
                        self.status_update.emit(self.gid, "✅ Re-added")
                        self.finished.emit(self.gid, True)
                        return

            self.status_update.emit(self.gid, "❌ Retry failed")
            self.finished.emit(self.gid, False)

        except Exception as e:
            print(f"❌ [RetryWorker] Error: {e}")
            self.finished.emit(self.gid, False)
