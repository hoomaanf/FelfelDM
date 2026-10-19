"""The per-download progress dialog and its pause/resume/cancel actions."""

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog

from ui.dialogs import DownloadProgressDialog


class ProgressDialogsMixin:
    """The per-download progress dialog and its pause/resume/cancel actions."""

    def _open_progress_dialog(self, gid: str) -> None:
        dl_data = self._all_downloads.get(gid, {})

        if gid in self._progress_dialogs:
            dialog = self._progress_dialogs[gid]
            try:
                if dialog.isVisible():
                    dialog.raise_()
                    dialog.activateWindow()
                    return
                else:
                    dialog.deleteLater()
                    del self._progress_dialogs[gid]
            except RuntimeError:
                del self._progress_dialogs[gid]

        dialog = DownloadProgressDialog(gid, dl_data, parent=None, main_window=self)
        name = dl_data.get("name", "")
        if name:
            dialog.setWindowTitle(name)

        dialog.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        dialog.setWindowModality(Qt.WindowModality.NonModal)

        dialog.pause_requested.connect(self._pause_from_dialog)
        dialog.resume_requested.connect(self._resume_from_dialog)
        dialog.cancel_requested.connect(self._cancel_from_dialog)
        dialog.cancel_with_delete_requested.connect(
            self._cancel_with_delete_from_dialog
        )
        dialog.speed_limit_changed.connect(self._set_download_speed_limit)

        dialog.finished.connect(
            lambda result, g=gid: self._on_progress_dialog_closed(g, result)
        )

        self._progress_dialogs[gid] = dialog
        dialog.show()
        self._center_dialog_on_screen(dialog)

        if dl_data.get("totalLength", 0) == 0:
            dialog.info_labels["size"].setText("Getting size...")

    def _on_progress_dialog_closed(self, gid: str, result=None) -> None:
        if gid in self._progress_dialogs:
            dialog = self._progress_dialogs.pop(gid)
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _close_progress_dialogs_for(self, gids: list) -> None:
        """Close any open DownloadProgressDialog for the given download ids.

        Called before removing a download from the UI/state so its progress
        window never lingers around showing stale data.
        """
        for gid in gids:
            if not gid:
                continue
            dialog = self._progress_dialogs.pop(gid, None)
            if dialog is None:
                continue
            try:
                dialog.close()
            except RuntimeError:
                pass
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _pause_from_dialog(self, gid: str) -> None:
        if not gid or gid not in self._all_downloads:
            return

        real_status = self._all_downloads[gid].get("status", "")
        if real_status in ["active", "waiting", "downloading"]:
            self._worker_pause(gid)
            self.store.save()
            self._refresh_table()
            self._update_queue_buttons()

    def _resume_from_dialog(self, gid: str) -> None:
        if not gid or gid not in self._all_downloads:
            return

        real_status = self._all_downloads[gid].get("status", "")
        download_type = self._all_downloads[gid].get("download_type", "normal")

        if download_type == "youtube":
            self._resume_youtube_download(gid)
            return

        if real_status == "error":
            print(f"🔄 Retrying error download from dialog: {gid}")
            self._retry_single_download(gid, manual=True)
            return

        if real_status == "paused":
            self._worker_resume(gid)

            self.store.mark_dirty()
            self._refresh_table()
            self._update_queue_buttons()
            return

        if real_status in ["waiting", "stopped"]:
            self._worker_resume(gid)
            self.store.mark_dirty()
            self._refresh_table()
            self._update_queue_buttons()

    def _cancel_from_dialog(self, gid: str) -> None:
        try:
            self._worker_remove(gid)
        except Exception:
            pass

        # Close the progress dialog (this method IS the cancel handler, so
        # the dialog is still open — pop and close it here).
        self._close_progress_dialogs_for([gid])

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        self._reset_speed_if_idle()

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._progress_dialog = None

    def _cancel_with_delete_from_dialog(self, gid: str) -> None:
        """Cancel a download and delete its files.

        Same ordering fix as _remove_with_files: stop aria2 FIRST,
        wait for the file handles to be released, THEN delete.
        """
        # Ask for confirmation FIRST, before touching aria2 or the UI.
        entries = self._collect_files_for_gids([gid])
        if entries:
            from ui.dialogs import DeleteFilesConfirmationDialog

            dlg = DeleteFilesConfirmationDialog(entries, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                print("🗑️ [Delete] Cancelled by user")
                return

        # ── Force-remove from aria2 FIRST ──
        try:
            aria2_gid = self._get_aria2_gid(gid) or gid
            self.aria2.force_remove(aria2_gid)
            print(f"🗑️ force_remove sent for {aria2_gid[:12]}")
        except Exception as e:
            print(f"❌ force_remove failed: {e}")
            try:
                self._worker_remove(gid)
            except Exception:
                pass

        # ── Wait for aria2 to actually release the file handles ──
        import time as _time

        deadline = _time.time() + 2.0
        while _time.time() < deadline:
            try:
                status = self.aria2.get_status(gid)
                if not status or status.get("status") in (None, "removed"):
                    break
            except Exception:
                break
            _time.sleep(0.1)

        # ── Now delete the files ──
        if entries:
            paths = [e["path"] for e in entries]
            deleted = 0
            for path in paths:
                try:
                    if not os.path.exists(path):
                        continue
                    if os.path.isdir(path):
                        print(f"⚠️ [Delete] Refusing to delete directory: {path}")
                        continue
                    if not os.path.isfile(path):
                        continue
                    os.remove(path)
                    deleted += 1
                    print(f"🗑️ DELETED: {os.path.basename(path)}")
                except OSError as e:
                    print(f"⚠️ Delete failed {path}: {e}")
            print(f"Deleted {deleted} file(s)")

        QApplication.processEvents()

        # Close the progress dialog for this download.
        self._close_progress_dialogs_for([gid])

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)
            if gid in q.downloads_info:
                del q.downloads_info[gid]

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        self._reset_speed_if_idle()

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._progress_dialog = None
