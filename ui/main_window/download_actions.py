"""Pause/resume/retry actions on selected downloads."""

from typing import Optional

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox


class DownloadActionsMixin:
    """Pause/resume/retry actions on selected downloads."""

    def _pause_selected(self) -> None:
        """Pause every selected download that is currently active/waiting."""
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]

        video_gids = []
        normal_gids = []

        for gid in gids:
            if gid not in self._all_downloads:
                continue
            dtype = self._all_downloads[gid].get("download_type", "normal")
            status = self._all_downloads[gid].get("status", "")

            if status not in ("active", "downloading"):
                continue

            if dtype == "video":
                video_gids.append(gid)
            else:
                normal_gids.append(gid)

        for gid in video_gids:
            self._pause_video_download(gid)

        if normal_gids:
            self._worker_pause_multi(normal_gids)

        self._refresh_table()
        self._update_queue_buttons()

    def _resume_selected(self) -> None:
        """Resume every selected download that is currently paused/waiting."""
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]

        for gid in gids:
            if gid not in self._all_downloads:
                continue

            dtype = self._all_downloads[gid].get("download_type", "normal")
            status = self._all_downloads[gid].get("status", "")

            if dtype == "video":
                if status == "paused":
                    self._resume_video_download(gid)
                continue

            if status == "error":
                self._retry_single_download(gid, manual=True)
                continue

            if status == "paused":
                self._worker_resume(gid)

        self.store.mark_dirty()
        self._refresh_table()
        self._update_queue_buttons()

    def _toggle_pause_resume(self) -> None:
        """Toggle pause/resume for all selected downloads.

        Logic:
        - If any is active/waiting → pause those (leave paused/error alone).
        - Else if any is paused → resume those (retry errored ones).
        - Else if exactly one error → retry it.
        - Otherwise → nothing.
        """
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]
        if not gids:
            return

        active_gids = []
        paused_gids = []
        error_gids = []

        for gid in gids:
            status = self._all_downloads.get(gid, {}).get("status", "")
            if status in ("active", "downloading"):
                active_gids.append(gid)
            elif status == "paused":
                paused_gids.append(gid)
            elif status == "error":
                error_gids.append(gid)

        if active_gids:
            self._pause_selected()
        elif paused_gids:
            self._resume_selected()
        elif len(error_gids) == 1:
            self._retry_single_download(error_gids[0], manual=True)

    def _retry_single_download(self, gid: str, manual: bool = False) -> None:
        """Retry a download.

        manual=True means the user explicitly clicked Retry: ask for
        confirmation, then reset the automatic retry budget to 0 so the
        download gets a fresh set of max_retry_attempts.

        manual=False (called by the delayed-retry scheduler) keeps the
        current count and enforces the cap silently.
        """
        if not gid or gid not in self._all_downloads:
            return

        if gid in self._retrying_gids:
            print(f"⏳ Already retrying {gid}")
            return

        max_retries = self.store.settings.get("max_retry_attempts", 5)
        error_count = self._to_int(self._all_downloads[gid].get("error_count", 0))

        if manual:
            # Ask the user before resetting. Text makes it clear that the
            # counter will start over, so they know what they're opting into.
            reply = QMessageBox.question(
                self,
                "Retry Download",
                "Do you want to try this download again?\n\n"
                "The retry counter will be reset to 0, so automatic retries "
                f"will be available again (up to {max_retries}).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            if error_count > 0:
                print(
                    f"🖐️ [Retry] Manual retry for {gid[:12]}: "
                    f"resetting error_count {error_count} → 0"
                )
            self._all_downloads[gid]["error_count"] = 0
            for q in self.store.queues:
                if gid in q.downloads_info:
                    q.downloads_info[gid]["error_count"] = 0
                    break
            error_count = 0
        elif error_count >= max_retries:
            # Automatic retry exhausted — stop silently, don't nag the user.
            print(
                f"⏹️ [Retry] Automatic retries exhausted for {gid[:12]} "
                f"({error_count}/{max_retries})"
            )
            return

        print(f"🔄 Retrying {gid} (attempt {error_count + 1}/{max_retries})")

        self._all_downloads[gid]["errorMessage"] = ""
        self._all_downloads[gid]["error_count"] = error_count + 1

        self._retrying_gids.add(gid)

        self.worker.re_add_requested.emit(gid)

        self._refresh_table()
        self._update_queue_buttons()

    def _re_add_download(self, gid: str) -> Optional[str]:
        if self.worker is None:
            return None
        self.worker.re_add_requested.emit(gid)
        return gid

    def _handle_re_add_result(self, result: dict) -> None:
        """Apply the outcome of a re-add to the download it belongs to.

        The worker reports the download id together with the result, so
        several retries in flight at once can never be mixed up.
        """
        req_id = result.get("id")
        new_gid = result.get("new")

        download_id = None
        if req_id in self._all_downloads:
            download_id = req_id
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == req_id:
                    download_id = did
                    break

        if not result.get("success") or not isinstance(new_gid, str):
            reason = result.get("error") or "re-add failed"
            print(f"❌ [Retry] Re-add failed for {str(req_id)[:12]}: {reason}")
            if download_id:
                # Release the "already retrying" lock.
                self._retrying_gids.discard(download_id)

                # Record the failure message (only if we don't already
                # have one — the original error may be more informative).
                if not self._all_downloads[download_id].get("errorMessage"):
                    self._all_downloads[download_id][
                        "errorMessage"
                    ] = f"Retry failed: {reason}"

                # C2 fix: a re-add failure is transient (aria2 busy,
                # momentary RPC drop, etc.), so schedule another retry
                # instead of leaving the download in 'error' forever.
                # _schedule_retry enforces the max_retries cap itself.
                error_count = self._to_int(
                    self._all_downloads[download_id].get("error_count", 0)
                )
                self._schedule_retry(download_id, error_count)
                self._refresh_table()
                self._update_queue_buttons()
            return

        if not download_id:
            print(f"⚠️ [Retry] No download found for new_gid={new_gid}")
            try:
                self.aria2.remove(new_gid)
            except Exception:
                pass
            return

        old_gid = self._all_downloads[download_id].get("aria2_gid")

        self._all_downloads[download_id]["aria2_gid"] = new_gid

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["aria2_gid"] = new_gid
                break

        self.store.save()

        self._retrying_gids.discard(download_id)

        print(
            f"[Retry] Complete: id={download_id[:12]} "
            f"aria2_gid: {old_gid} -> {new_gid}"
        )

        QTimer.singleShot(100, lambda g=new_gid: self.worker.resume_requested.emit(g))

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()
