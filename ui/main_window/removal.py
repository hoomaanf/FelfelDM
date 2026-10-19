"""Removing downloads (and their files)."""

import os
from typing import Any, Dict, List

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class RemovalMixin:
    """Removing downloads (and their files)."""

    def _remove_with_files(self) -> None:

        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        gids_to_remove = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_remove:
            return

        # ── STEP 1: Stop aria2 first, but ONLY after the user confirms ──
        # We still need to confirm before doing anything destructive.
        # So we collect the file list first, show the dialog, and only
        # then stop aria2.
        entries = self._collect_files_for_gids(gids_to_remove)
        if entries:
            from ui.dialogs import DeleteFilesConfirmationDialog

            dlg = DeleteFilesConfirmationDialog(entries, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                print("🗑️ [Delete] Cancelled by user")
                return
        else:
            print("🗑️ [Delete] No files to delete")

        # ── STEP 2: Force-remove each gid from aria2 first ──
        for gid in gids_to_remove:
            try:
                aria2_gid = self._get_aria2_gid(gid) or gid
                self.aria2.force_remove(aria2_gid)
                print(f"🗑️ [Delete] force_remove sent for {aria2_gid[:12]}")
            except Exception as e:
                print(f"⚠️ [Delete] force_remove failed for {gid}: {e}")
            try:
                self.aria2._call("aria2.removeDownloadResult", [gid])
            except Exception:
                pass

        # ── STEP 3: Give aria2 a moment to release the file handles ──
        # We poll until the gids are no longer reported by aria2, with
        # a hard cap so the UI can't hang.
        import time as _time

        deadline = _time.time() + 2.0
        remaining = set()
        while _time.time() < deadline:
            remaining = set()
            for gid in gids_to_remove:
                try:
                    status = self.aria2.get_status(gid)
                    if status and status.get("status") not in (None, "removed"):
                        remaining.add(gid)
                except Exception:
                    pass
            if not remaining:
                break
            _time.sleep(0.1)

        if remaining:
            print(
                f"⚠️ [Delete] {len(remaining)} download(s) still active in "
                f"aria2 after 2s; proceeding to delete files anyway"
            )

        # ── STEP 4: Now delete the files ──
        # Re-collect paths (aria2 may have just released the files) and
        # delete them with the same safe checks as before.
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
                except PermissionError as e:
                    print(f"⚠️ Permission denied: {path}: {e}")
                except OSError as e:
                    print(f"⚠️ Delete failed {path}: {e}")
                except Exception as e:
                    print(f"⚠️ Unexpected error deleting {path}: {e}")
            print(f"Deleted {deleted} file(s)")

        # ── STEP 5: Remove from UI + store ──
        self._close_progress_dialogs_for(gids_to_remove)
        # This action is explicitly "remove AND delete files", so the
        # yt-dlp worker is asked to clean up whatever it produced.
        self._cancel_youtube_workers_for(gids_to_remove, delete_files=True)

        for gid in gids_to_remove:
            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]
            if gid in self._all_downloads:
                del self._all_downloads[gid]

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _remove_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        gids_to_remove = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_remove:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Remove Downloads")
        dlg.setMinimumWidth(500)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel(f"Remove {len(gids_to_remove)} download(s)?"))
        layout.addWidget(QLabel("Choose what to do with the downloaded files:"))
        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_remove_only = QPushButton("Remove from List Only")
        btn_remove_files = QPushButton("Remove & Delete Files")
        btn_cancel = QPushButton("Cancel")
        btn_remove_only.setMinimumWidth(150)
        btn_remove_files.setMinimumWidth(150)
        btn_cancel.setMinimumWidth(100)
        btn_layout.addWidget(btn_remove_only)
        btn_layout.addWidget(btn_remove_files)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        result = {"value": None}

        def on_remove_only():
            result["value"] = "remove_only"
            dlg.accept()

        def on_remove_files():
            result["value"] = "remove_files"
            dlg.accept()

        def on_cancel():
            result["value"] = "cancel"
            dlg.reject()

        btn_remove_only.clicked.connect(on_remove_only)
        btn_remove_files.clicked.connect(on_remove_files)
        btn_cancel.clicked.connect(on_cancel)
        btn_remove_only.setDefault(True)

        dlg.exec()

        if result["value"] in (None, "cancel"):
            return

        delete_files = result["value"] == "remove_files"

        # If the user chose "Remove & Delete Files", show the confirmation
        # dialog FIRST — before touching any UI state — so cancelling is safe.
        if delete_files:
            if not self._delete_files_with_confirmation(gids_to_remove):
                return

        # Close any progress dialogs for these downloads first.
        self._close_progress_dialogs_for(gids_to_remove)

        # YouTube downloads are handled by a yt-dlp subprocess, not aria2.
        # Removing them from the list without cancelling the worker left the
        # process running (it is started in its own session) while the store
        # record was gone, so it kept writing files and -- because the
        # youtube store was never flushed -- the entry reappeared on restart.
        raw_gids = [self._get_aria2_gid(g) or g for g in gids_to_remove]
        self._cancel_youtube_workers_for(gids_to_remove, delete_files=delete_files)

        # Now remove from UI + aria2
        for gid in gids_to_remove:
            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]
            self._all_downloads.pop(gid, None)
            self._retrying_gids.discard(gid)
            self._size_unknown.discard(gid)

        try:
            self._worker_remove_multi([g for g in raw_gids if g])
        except Exception as e:
            print(f"⚠️ Batch remove failed: {e}")
            for gid in gids_to_remove:
                try:
                    self._worker_remove(gid)
                except Exception:
                    pass

        self._reset_speed_if_idle()
        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _clear_completed_downloads(self) -> None:
        q = self._current_queue()
        if not q:
            return

        completed_gids = [
            gid
            for gid in q.downloads
            if gid in self._all_downloads
            and self._all_downloads[gid].get("status", "") in ["complete", "completed"]
        ]

        if not completed_gids:
            QMessageBox.information(self, "Info", "No completed downloads to clear.")
            return

        if (
            QMessageBox.question(
                self,
                "Clear Completed",
                f"Remove {len(completed_gids)} completed download(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.No
        ):
            return

        self._close_progress_dialogs_for(completed_gids)

        for gid in completed_gids:
            try:
                self._worker_remove(gid)
            except Exception:
                pass

            if gid in q.downloads:
                q.downloads.remove(gid)
            if gid in self._all_downloads:
                del self._all_downloads[gid]

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()

    def _reset_speed_if_idle(self) -> None:
        has_active = any(
            self._all_downloads.get(g, {}).get("status") in ("active", "downloading")
            for g in self._all_downloads
        )
        if not has_active:
            self._speed_samples.clear()
            self._smooth_speed = 0
            self._last_calculated_global_speed = 0
            if hasattr(self, "speed_status_label"):
                self.speed_status_label.setText("0 B/s")

    def _download_has_started(self, info: dict) -> bool:
        """True when a download actually began, so it may have written files.

        A download that is only queued (or errored before any byte moved)
        must never have files attributed to it.
        """
        if not info:
            return False
        status = info.get("status", "")
        if status in ("active", "downloading", "complete", "completed"):
            return True
        return self._to_int(info.get("completedLength", 0)) > 0

    def _collect_files_for_gids(self, gids: List[str]) -> List[Dict[str, Any]]:
        """Build a list of files that WOULD be deleted for the given gids.

        Each entry is:
            {
                "gid": download_id,
                "path": absolute file path,
                "name": basename,
                "size": int (bytes) or 0,
                "kind": "main" | "sidecar",
                "exists": bool,
            }
        """
        entries: List[Dict[str, Any]] = []
        seen_paths: set = set()

        for gid in gids:
            file_paths: List[str] = []

            info = None
            for q in self.store.queues:
                if gid in q.downloads_info:
                    info = q.downloads_info[gid]
                    break

            runtime = self._all_downloads.get(gid)
            if info is None:
                info = runtime
            if info is None:
                continue

            # ── 1. Collect the file paths aria2 actually reported ──
            # A download that was only queued has a *predicted* path here
            # (built from the URL) but no file on disk yet, and it keeps
            # that path even after aria2 starts reporting it. So a path is
            # only treated as deletable when the download has actually
            # started AND the file exists. Without both checks a
            # never-started download could claim a pre-existing same-named
            # file in the user's folder and offer to delete it.
            started = self._download_has_started(info)
            candidate_paths: List[str] = []

            for f in info.get("files", []) or []:
                p = f.get("path")
                if p and p not in candidate_paths:
                    candidate_paths.append(p)

            # Also consider the runtime dict if it has additional paths not
            # present in downloads_info (rare, but possible right after a
            # re-add).
            runtime_info = self._all_downloads.get(gid)
            if runtime_info is not None:
                for f in runtime_info.get("files", []) or []:
                    p = f.get("path")
                    if p and p not in candidate_paths:
                        candidate_paths.append(p)

            if started:
                file_paths = [p for p in candidate_paths if os.path.isfile(p)]
            else:
                file_paths = []

            # ── 2. Add .aria2 sidecars for the known main files ──
            # aria2 always writes "<target>.aria2" next to the target
            # while the download is in progress or paused. We only add
            # it if the main file path is already known — never as a
            # free-floating guess.
            aria2_sidecars: List[str] = []
            for p in file_paths:
                sidecar = p + ".aria2"
                if sidecar not in aria2_sidecars:
                    aria2_sidecars.append(sidecar)

            # ── 3. Build entries ──
            for p in file_paths:
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                exists = os.path.exists(p)
                try:
                    size = os.path.getsize(p) if exists else 0
                except OSError:
                    size = 0
                entries.append(
                    {
                        "gid": gid,
                        "path": p,
                        "name": os.path.basename(p),
                        "size": size,
                        "kind": "main",
                        "exists": exists,
                    }
                )

            for p in aria2_sidecars:
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                exists = os.path.exists(p)
                try:
                    size = os.path.getsize(p) if exists else 0
                except OSError:
                    size = 0
                entries.append(
                    {
                        "gid": gid,
                        "path": p,
                        "name": os.path.basename(p),
                        "size": size,
                        "kind": "sidecar",
                        "exists": exists,
                    }
                )

        return entries

    def _delete_files_with_confirmation(self, gids: List[str]) -> bool:

        entries = self._collect_files_for_gids(gids)
        if not entries:
            print("🗑️ [Delete] No files to delete")
            return True

        from ui.dialogs import DeleteFilesConfirmationDialog

        dlg = DeleteFilesConfirmationDialog(entries, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            print("🗑️ [Delete] Cancelled by user")
            return False

        paths = dlg.get_paths_to_delete()
        if not paths:
            print("🗑️ [Delete] Nothing selected")
            return True

        deleted = 0
        for path in paths:
            try:
                # Re-validate: must be a regular file, must exist.
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
            except PermissionError as e:
                print(f"⚠️ Permission denied: {path}: {e}")
            except OSError as e:
                print(f"⚠️ Delete failed {path}: {e}")
            except Exception as e:
                print(f"⚠️ Unexpected error deleting {path}: {e}")

        print(f"Deleted {deleted} file(s)")
        return True
