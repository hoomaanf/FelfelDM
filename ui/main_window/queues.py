"""Queues: list, create/edit/delete, start/pause, schedules, moving downloads."""

from typing import Optional

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from core import Queue, QueueOperationWorker, ScheduleConfig
from ui.dialogs import QueueSettingsDialog
from utils.helpers import get_icon


class QueuesMixin:
    """Queues: list, create/edit/delete, start/pause, schedules, moving downloads."""

    def _ensure_default_queue(self) -> None:
        if not self.store.queues:
            default_queue = Queue("Default", paused=True)
            self.store.queues.append(default_queue)
            self.store.save()

    def _current_queue(self) -> Optional[Queue]:
        if 0 <= self._current_queue_idx < len(self.store.queues):
            return self.store.queues[self._current_queue_idx]
        return None

    def _get_or_create_queue(self, queue_name: str) -> Queue:
        for q in self.store.queues:
            if q.name == queue_name:
                return q

        target_queue = Queue(queue_name, paused=False)
        if queue_name == "__direct__":
            target_queue.max_concurrent = 99
        self.store.queues.insert(0, target_queue)
        self.store.save()
        return target_queue

    def _refresh_queue_list(self) -> None:
        """Refresh the queue list with proper status indicators"""

        if not self._queue_list_dirty:
            return

        self._queue_list_dirty = False

        self.queue_list.blockSignals(True)
        self.queue_list.clear()

        something_changed = False

        for q in self.store.queues:
            if len(q.downloads) == 0:
                if q.paused != True or q.manually_paused != False:
                    something_changed = True
                q.paused = True
                q.manually_paused = False
                for gid in q.downloads[:]:
                    self._all_downloads.pop(gid, None)
                q.downloads.clear()

            if q.name == "__direct__":
                item = QListWidgetItem(
                    get_icon("media-playback-start"), "Direct Downloads"
                )
                item.setForeground(QColor("#3498db"))
            else:
                item = QListWidgetItem(q.name)

                if q.paused:
                    item.setIcon(get_icon("media-playback-pause"))
                    item.setForeground(QColor("#f39c12"))
                else:
                    has_active = any(
                        gid in self._all_downloads
                        and self._all_downloads[gid].get("status", "")
                        in ["active", "waiting", "downloading"]
                        for gid in q.downloads
                    )
                    if has_active:
                        item.setIcon(get_icon("media-playback-start"))
                        item.setForeground(QColor("#27ae60"))
                    else:
                        item.setIcon(get_icon("media-playback-start"))
                        item.setForeground(QColor("#3498db"))

            self.queue_list.addItem(item)

        if self.store.queues:
            self._current_queue_idx = min(
                self._current_queue_idx, len(self.store.queues) - 1
            )
            self.queue_list.setCurrentRow(self._current_queue_idx)

        self.queue_list.blockSignals(False)
        self._update_queue_status()
        self._update_queue_buttons()

        if something_changed:
            self.store.save()

    def _on_queue_changed(self, idx: int) -> None:
        if idx >= 0:
            self._current_queue_idx = idx
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            self._refresh_table()
            q = self._current_queue()
            if q and not q.paused:
                self._apply_settings_to_aria2()

    def _next_queue(self) -> None:
        """Switch to next queue"""
        if self.queue_list.count() > 0:
            current = self.queue_list.currentRow()
            next_idx = (current + 1) % self.queue_list.count()
            self.queue_list.setCurrentRow(next_idx)

    def _prev_queue(self) -> None:
        """Switch to previous queue"""
        if self.queue_list.count() > 0:
            current = self.queue_list.currentRow()
            prev_idx = (current - 1) % self.queue_list.count()
            self.queue_list.setCurrentRow(prev_idx)

    def _add_queue(self) -> None:
        name, ok = QInputDialog.getText(self, "New Queue", "Queue name:")
        if not ok:
            return

        name = (name or "").strip()
        if not name:
            return

        if name == "Default":
            QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
            return

        # A queue name is used as a dictionary key for schedules and proxies,
        # so duplicates would silently shadow each other.
        if any(q.name == name for q in self.store.queues):
            QMessageBox.warning(
                self, "Error", f"A queue named '{name}' already exists."
            )
            return

        new_queue = Queue(name, paused=True)
        self.store.queues.append(new_queue)
        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _edit_queue(self) -> None:
        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        dlg = QueueSettingsDialog(q, self)
        self._show_singleton_dialog(
            f"queue_settings:{id(q)}",
            dlg,
            on_accepted=lambda dlg, q=q: self._process_edit_queue(dlg, q),
        )

    def _process_edit_queue(self, dlg: "QueueSettingsDialog", q: Queue) -> None:
        d = dlg._cached_data
        if not d:
            return

        new_name = (d.get("name") or "").strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Queue name is required.")
            return

        # "Default" is reserved for NEW queues — but editing the existing
        # Default queue without renaming it is fine, so only reject the
        # name when the queue is actually being renamed TO it.
        if new_name == "Default" and q.name != "Default":
            QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
            return

        # Renaming onto an existing queue name would make the two share a
        # schedule/proxy key and shadow each other.
        if new_name != q.name and any(
            other.name == new_name for other in self.store.queues
        ):
            QMessageBox.warning(
                self, "Error", f"A queue named '{new_name}' already exists."
            )
            return

        old_name = q.name
        q.name = new_name
        q.save_path = d["save_path"]
        q.max_concurrent = d["max_concurrent"]
        self.store.settings["max_concurrent"] = d["max_concurrent"]
        q.schedule_enabled = d["schedule_enabled"]
        q.schedule_start = d["schedule_start"]
        q.schedule_end = d["schedule_end"]
        q.days = d["days"]
        q.speed_limit = d.get("speed_limit", 0)
        q.proxy_config = d.get("proxy_config")
        q.manually_paused = False

        if q.proxy_config:
            self.proxy_manager.set_queue_proxy(q.name, q.proxy_config)
        else:
            self.proxy_manager.remove_queue_proxy(q.name)

        # Drop the old name's proxy entry, otherwise a rename leaves a stale
        # key behind that can be handed out for the previous name.
        if old_name != q.name:
            self.proxy_manager.remove_queue_proxy(old_name)

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()
        self._apply_settings_to_aria2()
        if getattr(self, "worker", None):
            self.worker._start_next_pending_video()

        if q.speed_limit > 0:
            self.aria2.change_global_option({"max-overall-download-limit": "0"})
            print(f"⚡ [SpeedLimit] Global disabled (queue '{q.name}' has limit)")
        self._load_schedules()
        self._apply_queue_speed_limit(q)

    def _delete_queue(self) -> None:
        q = self._current_queue()
        if not q or len(self.store.queues) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete the last queue.")
            return

        if (
            QMessageBox.question(self, "Delete", f"Delete queue '{q.name}'?")
            == QMessageBox.StandardButton.Yes
        ):
            self.store.queues.pop(self._current_queue_idx)
            self._current_queue_idx = 0
            self.store.save()
            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._update_queue_buttons()

    def _move_queue_up(self) -> None:
        current_row = self.queue_list.currentRow()
        if current_row <= 0:
            return

        self.store.queues.insert(current_row - 1, self.store.queues.pop(current_row))
        self._current_queue_idx = current_row - 1

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(self._current_queue_idx)
        self._on_queue_changed(self._current_queue_idx)

    def _move_queue_down(self) -> None:
        current_row = self.queue_list.currentRow()
        if current_row < 0 or current_row >= len(self.store.queues) - 1:
            return

        self.store.queues.insert(current_row + 1, self.store.queues.pop(current_row))
        self._current_queue_idx = current_row + 1

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(self._current_queue_idx)
        self._on_queue_changed(self._current_queue_idx)

    def _move_selected_to_queue(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        gids_to_move = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_move:
            return

        source_queue = self._current_queue()
        if not source_queue:
            return

        target_queues = [
            q
            for q in self.store.queues
            if q.name != source_queue.name and q.name != "__direct__"
        ]
        if not target_queues:
            QMessageBox.warning(self, "Error", "No other queues available.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Move to Queue")
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"Move {len(gids_to_move)} download(s) to:"))
        queue_combo = QComboBox()
        for q in target_queues:
            queue_combo.addItem(q.name, q)
        layout.addWidget(queue_combo)

        btn_layout = QHBoxLayout()
        btn_move = QPushButton("Move")
        btn_move.setIcon(get_icon("go-next"))
        btn_cancel = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_move)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        result = None

        def on_move():
            nonlocal result
            result = queue_combo.currentData()
            dlg.accept()

        def on_cancel():
            nonlocal result
            result = None
            dlg.reject()

        btn_move.clicked.connect(on_move)
        btn_cancel.clicked.connect(on_cancel)

        dlg.exec()

        if result is None:
            return

        target_queue = result

        for gid in gids_to_move:
            if gid in source_queue.downloads:
                source_queue.downloads.remove(gid)

            if gid not in target_queue.downloads:
                target_queue.downloads.append(gid)

            if gid in source_queue.downloads_info:
                info = source_queue.downloads_info.pop(gid)
                target_queue.downloads_info[gid] = info

            was_paused = self._all_downloads.get(gid, {}).get("status") == "paused"

            if target_queue.paused:
                if not was_paused:
                    self._worker_pause(gid)
            else:
                if was_paused:
                    self._worker_resume(gid)

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()

        self._apply_queue_speed_limit(target_queue)

    def _show_schedule_info(self, q: Queue) -> None:
        next_time = q.get_next_schedule_time()
        if next_time:
            time_str = next_time.strftime("%H:%M on %A")
            QMessageBox.information(
                self,
                "Queue Scheduled",
                f"This queue is scheduled to start at {time_str}.\n\n"
                f"It will start automatically at that time.",
                QMessageBox.StandardButton.Ok,
            )
        else:
            QMessageBox.information(
                self,
                "Queue Scheduled",
                "This queue is scheduled but no upcoming time found.",
                QMessageBox.StandardButton.Ok,
            )

    def _load_schedules(self):
        schedules = []
        for q in self.store.queues:
            if q.schedule_enabled:
                schedules.append(
                    ScheduleConfig(
                        queue_name=q.name,
                        start=q.schedule_start,
                        end=q.schedule_end,
                        days=set(q.days),
                        enabled=True,
                    )
                )

        # Only push to the schedule thread if something actually changed.
        # _load_schedules is called from several places (startup, queue edit,
        # settings save) and re-pushing an identical schedule list churns the
        # manager's _running_queues set, causing spurious start/pause signals.
        fingerprint = hash(
            tuple(
                sorted(
                    (s.queue_name, s.start, s.end, tuple(sorted(s.days)))
                    for s in schedules
                )
            )
        )
        if fingerprint == self._last_schedules_hash:
            return

        self._last_schedules_hash = fingerprint
        self.schedule_thread.set_schedules(schedules)
        print(f"📅 [Schedule] Loaded {len(schedules)} schedule(s)")

    def _on_schedule_start(self, queue_name: str):
        """UI notification that the scheduler has started a queue.

        The scheduler already did the real work (unpaused aria2
        downloads, updated the store). We need to:
          1. Reload the queue's paused flag from the store, because
             the scheduler may have changed it while the UI was
             frozen (Wayland lock).
          2. Refresh the UI so the user sees the new state.
        """
        print(f"🔔 [UI] Scheduler started queue: {queue_name}")

        for i, q in enumerate(self.store.queues):
            if q.name != queue_name:
                continue

            # The scheduler thread only unpauses downloads aria2 still
            # knows. It cannot start Video downloads, retry errored or
            # stopped ones, or re-add downloads aria2 has forgotten, so a
            # scheduled queue could log "started" and download nothing.
            # Run the same logic as the Start button for those.
            #
            # (The old code copied the scheduler's optimistic "active"
            # status into the UI here, which showed downloads as running
            # that had not been started at all.)
            # The scheduler also emits this signal when it skipped a queue
            # the user paused by hand; that must stay paused.
            if q.name != "__direct__" and not getattr(q, "manually_paused", False):
                try:
                    self._start_queue_downloads(q)
                except Exception as e:
                    print(f"⚠️ [UI] Scheduled start of '{queue_name}' failed: {e}")

            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._refresh_table()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            break

    def _on_schedule_pause(self, queue_name: str):
        """UI notification that the scheduler has paused a queue."""
        print(f"🔔 [UI] Scheduler paused queue: {queue_name}")

        for i, q in enumerate(self.store.queues):
            if q.name != queue_name:
                continue

            for gid in q.downloads:
                info = q.downloads_info.get(gid)
                if not info:
                    continue

                # The scheduler thread skips Video downloads (it cannot
                # talk to the yt-dlp workers), so without this they kept
                # downloading after the schedule window ended.
                dl = self._all_downloads.get(gid)
                if (
                    dl is not None
                    and dl.get("download_type") == "video"
                    and dl.get("status") in ("downloading", "active", "waiting")
                ):
                    self._pause_video_download(gid)
                    dl["status"] = "paused"
                    info["status"] = "paused"

                new_status = info.get("status", "")
                if gid in self._all_downloads and new_status:
                    self._all_downloads[gid]["status"] = new_status
                    if new_status == "paused":
                        self._all_downloads[gid]["downloadSpeed"] = 0

            self._reset_queue_retry_state(q)
            self.store.save()
            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._refresh_table()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            break

    def _start_current_queue(self) -> None:
        """Start the entire queue"""
        print("▶️ Starting queue...")

        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        if q.schedule_enabled and not q.is_scheduled_now():
            self._show_schedule_info(q)
            return

        self._start_queue_downloads(q)

    def _start_queue_downloads(self, q) -> None:
        """Start every download of `q` (also used by the scheduler).

        Retries errored/stopped downloads, resumes the rest in aria2 and
        starts the Video ones. Shared by the Start button and the
        schedule so both behave the same.
        """
        error_gids = []
        normal_gids = []
        video_gids = []

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                dtype = self._all_downloads[gid].get("download_type", "normal")

                if dtype == "video":
                    video_gids.append(gid)
                    continue

                if status in ["error", "stopped"]:
                    error_gids.append(gid)
                else:
                    normal_gids.append(gid)

        for gid in error_gids:
            print(f"🔄 Retrying error download from queue start: {gid}")
            self._retry_single_download(gid)

        for gid in normal_gids:
            if gid in self._all_downloads:
                self._all_downloads[gid]["error_count"] = 0
                self._all_downloads[gid]["errorMessage"] = ""

        q.manually_paused = False
        self._apply_settings_to_aria2()
        q.paused = False
        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()

        if normal_gids:
            temp_queue = Queue(q.name, paused=False)
            temp_queue.downloads = normal_gids
            for gid in normal_gids:
                if gid in q.downloads_info:
                    temp_queue.downloads_info[gid] = q.downloads_info[gid]

            self._queue_worker = QueueOperationWorker(temp_queue, "start", self)
            self._connect_queue_worker_signals()
            self._queue_worker.start()
        else:
            self._queue_worker = None

        for gid in video_gids:
            print(f"🎬 Starting Video download from queue start: {gid}")
            self._start_video_download(gid)

        self.start_queue_btn.setEnabled(False)
        self.pause_queue_btn.setEnabled(False)
        self._last_speed_limit_active_count = None
        self._apply_queue_speed_limit(q)

    def _reset_queue_retry_state(self, q: Queue) -> None:
        """Reset failed-attempt counters when a queue is paused.

        Pausing is a natural "give up for now" point: the user (or the
        schedule) stops the queue because the network is bad / it's
        daytime / whatever. When it's started again — possibly hours
        later, after fixing Wi-Fi, connecting a VPN, etc. — the
        download should get a fresh retry budget. Otherwise a queue
        paused overnight stays blocked by counters that ran up
        against a momentary outage.

        Also cancels any pending retry timer/countdown for the
        queue's downloads, so a stale timer can't fire after pause.
        """
        reset_count = 0
        for gid in q.downloads:
            # Cancel any pending retry timer / countdown for this download
            timer = self._retry_timers.pop(gid, None)
            if timer is not None:
                try:
                    timer.stop()
                except Exception:
                    pass
            self._retry_state.pop(gid, None)
            self._retrying_gids.discard(gid)

            data = self._all_downloads.get(gid)
            if data is None:
                continue

            # Clear transient retry UI state ("Retrying in Ns...")
            data.pop("status_detail", None)

            if self._to_int(data.get("error_count", 0)) > 0:
                data["error_count"] = 0
                reset_count += 1

            info = q.downloads_info.get(gid)
            if info and self._to_int(info.get("error_count", 0)) > 0:
                info["error_count"] = 0

        if reset_count:
            print(
                f"♻️ [Pause] Reset error_count for {reset_count} "
                f"download(s) in queue '{q.name}'"
            )

    def _pause_current_queue(self):
        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        if q.schedule_enabled:
            q.schedule_enabled = False
            q.manually_paused = True
            self.tray.showMessage(
                "FelfelDM",
                f"⏸️ Queue '{q.name}' paused manually.\n⏰ Schedule disabled.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

        q.paused = True
        q.manually_paused = True
        self._reset_queue_retry_state(q)
        self.store.save()

        # Ask aria2 directly which gids are currently active/waiting.
        # We cannot trust _all_downloads[gid]["status"] here because
        # the scheduler may have changed aria2's state while the UI
        # was frozen (Wayland lock).
        #
        # IMPORTANT: we collect *download_ids* (not aria2 gids) here,
        # because _worker_pause_multi expects download_ids and will
        # translate them to aria2 gids itself. Sending aria2 gids
        # would cause _get_aria2_gid() to return None for each one,
        # silently dropping every gid — which is exactly why the
        # queue was "paused" in the UI but still downloading.
        download_ids_to_pause = []
        for gid in q.downloads:
            info = q.downloads_info.get(gid, {})
            dtype = info.get("download_type", "normal")

            if dtype == "video":
                # Video handled via the existing _pause_video_download path.
                if gid in self._all_downloads:
                    st = self._all_downloads[gid].get("status", "")
                    if st in ("downloading", "active", "waiting"):
                        self._pause_video_download(gid)
                        self._all_downloads[gid]["status"] = "paused"
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "paused"
                continue

            aria2_gid = info.get("aria2_gid")
            if not aria2_gid:
                continue

            # Ask aria2 for the real status.
            real_status = ""
            try:
                st = self.aria2.get_status(aria2_gid)
                if st:
                    real_status = st.get("status", "")
            except Exception:
                pass

            # If aria2 reports the download is active or waiting, we
            # want to pause it. We use the download_id (gid), not the
            # aria2 gid, because _worker_pause_multi resolves the
            # aria2 gid from _all_downloads itself.
            if real_status in ("active", "waiting", "paused"):
                download_ids_to_pause.append(gid)

        if download_ids_to_pause:
            print(
                f"⏸️ [UI] Pausing queue '{q.name}': "
                f"{len(download_ids_to_pause)} download(s)"
            )
            self._worker_pause_multi(download_ids_to_pause)
        else:
            print(f"⏸️ [UI] Queue '{q.name}' has no active downloads to pause")

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        self.tray.showMessage(
            "FelfelDM",
            f"⏸️ Queue '{q.name}' paused",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    def _on_queue_operation_finished(self, success: bool, message: str) -> None:

        self.start_queue_btn.setEnabled(True)
        self.pause_queue_btn.setEnabled(True)

        self.status_label.setText(message)
        self.tray.showMessage(
            "FelfelDM",
            message,
            (
                QSystemTrayIcon.MessageIcon.Information
                if success
                else QSystemTrayIcon.MessageIcon.Warning
            ),
            5000,
        )

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        q = self._current_queue()
        if q:
            self._apply_queue_speed_limit(q)

        self._queue_worker = None
