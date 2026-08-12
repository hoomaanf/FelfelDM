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

        # Split out YouTube pseudo-downloads first (they don't go through
        # aria2 at all) so the rest can be handled as a normal-download
        # batch via multicall.
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
        error_count = 0

        for gid in youtube_gids:
            real_status = self._all_downloads.get(gid, {}).get("status", "")
            if real_status == "paused":
                self.worker.resume_youtube_download(gid)
                self.download_status_changed.emit(gid, "downloading")
                resumed_count += 1
                self.status_update.emit(f"Resuming YouTube: {gid[:8]}...")

        if normal_gids:
            # One multicall for every download's real aria2-side status,
            # instead of one aria2.tellStatus round trip per gid.
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
                    self.status_update.emit(f"Re-adding: {gid[:8]}...")
                    self.worker.re_add_requested.emit(gid)
                    resumed_count += 1
                    continue

                real_status = status_data.get("status", "unknown")

                if real_status in ["paused", "waiting", "error"]:
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
                # One multicall to resume everything that needs it, instead
                # of a separate resume_requested signal (and blocking RPC)
                # per download.
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

        self.retry_delay = main_window.store.settings.get("retry_delay", 1.0)
        self.retry_delay_ms = int(self.retry_delay * 1000)

    def stop(self):
        self._should_stop = True

    def _wait(self, ms: int):
        # Plain blocking sleep in small chunks, checking the stop flag as
        # we go — this replaces a previous QEventLoop + QTimer.singleShot
        # based wait. That pattern creates Qt objects whose thread
        # affinity depends on exactly which thread is executing at the
        # moment, and could trigger "QObject::startTimer: Timers cannot
        # be started from another thread". msleep() is a plain blocking
        # call with no QObject involved, so it can't hit that issue.
        remaining = ms
        step = 50
        while remaining > 0 and not self._should_stop:
            chunk = min(step, remaining)
            self.msleep(chunk)
            remaining -= chunk

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
