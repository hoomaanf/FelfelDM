"""Queue/status labels, buttons, progress bar and speed display."""

import time

from PyQt6.QtWidgets import QLabel

from core import Queue
from utils.helpers import format_size, format_speed, get_icon


class StatusDisplayMixin:
    """Queue/status labels, buttons, progress bar and speed display."""

    def _update_queue_buttons(self) -> None:
        q = self._current_queue()
        current_row = self.queue_list.currentRow()
        total_queues = len(self.store.queues)

        self.move_up_btn.setEnabled(current_row > 0)
        self.move_down_btn.setEnabled(0 <= current_row < total_queues - 1)

        if not q or len(q.downloads) == 0 or q.name == "__direct__":
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)

            if q and q.name == "__direct__":
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Direct Downloads",
                    "folder-download",
                    "#3498db",
                    size=18,
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Empty",
                    "folder-open",
                    "#95a5a6",
                    size=18,
                )
            return

        has_active = False
        has_paused = False
        has_error = False
        has_getting_size = False

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                total = self._to_int(self._all_downloads[gid].get("totalLength", 0))

                if total == 0 and status in ["waiting", "paused"]:
                    has_getting_size = True

                if status in ["active", "downloading"]:
                    has_active = True
                elif status == "paused" and total > 0:
                    has_paused = True
                elif status == "error":
                    has_error = True

        has_resumable = has_paused or has_error or has_getting_size

        if q.paused:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Paused",
                "media-playback-pause",
                "#f39c12",
                size=18,
            )

            if has_active:
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            elif has_resumable:
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            else:
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(False)
        else:

            if has_active:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Running",
                    "media-playback-start",
                    "#27ae60",
                    size=18,
                )
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(True)
            elif has_resumable:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(False)

    def _update_queue_status(self) -> None:
        q = self._current_queue()
        if not q:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "No Queue",
                "dialog-question",
                "#95a5a6",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Ready")
            return

        if q.name == "__direct__":
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Direct Downloads",
                "folder-download",
                "#3498db",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Direct Downloads")
            return

        if len(q.downloads) == 0:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Empty",
                "folder-open",
                "#95a5a6",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("Add downloads to start")
            self.status_label.setText("Empty queue")
            return

        if getattr(q, "speed_limit", 0) > 0:
            self.speed_limit_lbl.setText(f"Speed Limit: {q.speed_limit} KB/s")
            self.speed_limit_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:
            self.speed_limit_lbl.setText("")

        all_complete = True
        has_any_download = False
        for gid in q.downloads:
            has_any_download = True
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status not in ["complete", "error", "removed"]:
                    all_complete = False
                    break
            else:
                all_complete = False
                break

        if all_complete and has_any_download:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Complete",
                "emblem-default",
                "#27ae60",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("All downloads complete")
            return

        if q.schedule_enabled:
            self._update_scheduled_queue_status(q)
        else:
            self._update_regular_queue_status(q)

    def _set_status_with_icon(
        self,
        text_label: QLabel,
        icon_label: QLabel,
        text: str,
        icon_name: str,
        color: str,
        size: int = 16,
    ) -> None:
        """Set a status label's text plus a themed icon next to it.

        Falls back to a colored Unicode bullet if the theme has no
        matching icon, so the layout never collapses.
        """
        text_label.setText(text)
        text_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        icon = get_icon(icon_name)
        if icon is not None and not icon.isNull():
            pm = icon.pixmap(size, size)
            if not pm.isNull():
                icon_label.setPixmap(pm)
                icon_label.setStyleSheet("")
                return

        # Fallback: colored bullet
        icon_label.clear()
        icon_label.setText("●")
        icon_label.setStyleSheet(f"color: {color}; font-size: {size}px;")

    def _update_scheduled_queue_status(self, q: Queue) -> None:
        if q.is_scheduled_now():
            if not q.paused:
                has_active = any(
                    gid in self._all_downloads
                    and self._all_downloads[gid].get("status", "")
                    in ["active", "waiting", "downloading"]
                    for gid in q.downloads
                )
                if has_active:
                    self._set_status_with_icon(
                        self.queue_status_lbl,
                        self.queue_status_icon,
                        "Running",
                        "media-playback-start",
                        "#27ae60",
                        size=18,
                    )
                else:
                    self._set_status_with_icon(
                        self.queue_status_lbl,
                        self.queue_status_icon,
                        "Waiting",
                        "appointment-soon",
                        "#3498db",
                        size=18,
                    )

                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    "Schedule active",
                    "alarm-clock",
                    "#27ae60",
                    size=14,
                )
                self.status_label.setText("Scheduled time is active")
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Waiting",
                    "appointment-soon",
                    "#f39c12",
                    size=18,
                )
                next_time = q.get_next_schedule_time()
                if next_time:
                    wait_text = f"Starts at {next_time.strftime('%H:%M')}"
                else:
                    wait_text = "Waiting for schedule"
                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    wait_text,
                    "alarm-clock",
                    "#3498db",
                    size=14,
                )
                self.status_label.setText("Waiting for scheduled time")
        else:
            days_text = ", ".join(
                ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days
            )
            next_time = q.get_next_schedule_time()
            if next_time:
                next_text = f"Next: {next_time.strftime('%H:%M on %A')}"
            else:
                next_text = (
                    f"Next: {q.schedule_start.strftime('%H:%M')}-"
                    f"{q.schedule_end.strftime('%H:%M')} {days_text}"
                )
            self._set_status_with_icon(
                self.schedule_status_lbl,
                self.schedule_status_icon,
                next_text,
                "appointment-soon",
                "#3498db",
                size=14,
            )

            if q.paused:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused (waiting)",
                    "media-playback-pause",
                    "#f39c12",
                    size=18,
                )
                self.status_label.setText(
                    f"Paused - Next: {q.schedule_start.strftime('%H:%M')}"
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Waiting for schedule",
                    "appointment-soon",
                    "#3498db",
                    size=18,
                )
                self.status_label.setText(
                    f"Waiting: {q.schedule_start.strftime('%H:%M')}"
                )

    def _update_regular_queue_status(self, q: Queue) -> None:
        if q.paused:
            has_resumable = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "") in ["paused", "waiting"]
                for gid in q.downloads
            )
            if has_resumable:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused",
                    "media-playback-pause",
                    "#f39c12",
                    size=18,
                )
                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    "Click Start to resume",
                    "media-playback-start",
                    "#3498db",
                    size=14,
                )
                self.status_label.setText("Paused")
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused",
                    "media-playback-pause",
                    "#95a5a6",
                    size=18,
                )
                self.schedule_status_icon.clear()
                self.schedule_status_lbl.setText("")
                self.status_label.setText("Paused")
        else:
            has_active = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "")
                in ["active", "downloading"]
                for gid in q.downloads
            )
            if has_active:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Running",
                    "media-playback-start",
                    "#27ae60",
                    size=18,
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Running")

    def _update_progress_bar(self) -> None:
        q = self._current_queue()
        total_size = 0
        completed_size = 0

        if not q or q.name == "__direct__":
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Direct Downloads — no queue")
            return

        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid]
                total_size += int(row.get("totalLength", 0))
                completed_size += int(row.get("completedLength", 0))

        speed_texts = []
        global_limit = self.store.settings.get("speed_limit", 0)
        if global_limit > 0:
            speed_texts.append(
                f"Global: {global_limit//1024} MB/s"
                if global_limit >= 1024
                else f"Global: {global_limit} KB/s"
            )

        if q and getattr(q, "speed_limit", 0) > 0:
            q_limit = q.speed_limit
            speed_texts.append(
                f"Queue: {q_limit//1024} MB/s"
                if q_limit >= 1024
                else f"Queue: {q_limit} KB/s"
            )

        speed_part = " | " + " | ".join(speed_texts) if speed_texts else ""

        if total_size > 0:
            progress = int((completed_size / total_size) * 100)
            self.progress_bar.setValue(min(progress, 100))
            self.progress_bar.setFormat(
                f"{format_size(completed_size)} / {format_size(total_size)} ({progress}%){speed_part}"
            )
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"No active downloads{speed_part}")

    def _update_toggle_button(self) -> None:
        if not hasattr(self, "table") or not self.table.selectionModel():
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            self.btn_move_queue.setEnabled(False)
            return

        selected_indexes = self.table.selectionModel().selectedRows()
        if not selected_indexes:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            self.btn_move_queue.setEnabled(False)
            return

        self.btn_move_queue.setEnabled(True)

        # Gather statuses of all selected downloads
        statuses = []
        for idx in selected_indexes:
            gid = self.model.get_gid(idx.row())
            if not gid:
                continue
            status = self._all_downloads.get(gid, {}).get("status", "")
            if status:
                statuses.append(status)

        if not statuses:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        total = len(statuses)
        active_count = sum(1 for s in statuses if s in ("active", "downloading"))
        paused_count = sum(1 for s in statuses if s == "paused")
        error_count = sum(1 for s in statuses if s == "error")
        waiting_count = sum(1 for s in statuses if s == "waiting")

        if waiting_count == total:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Waiting")
            self.btn_toggle.setIcon(get_icon("clock"))
            return

        # Single error → Retry
        if error_count == 1 and total == 1:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Retry")
            self.btn_toggle.setIcon(get_icon("view-refresh"))
            return

        # All active → Pause
        if active_count == total:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        # All paused → Resume
        if paused_count == total:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon("media-playback-start"))
            return

        # Mixed: if any active → Pause (only active ones will be paused)
        if active_count > 0:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        # Mixed: if any paused (no active) → Resume (only paused ones resumed)
        if paused_count > 0:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon("media-playback-start"))
            return

        # Nothing actionable (all complete/retrying/etc.)
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.setText("Pause")
        self.btn_toggle.setIcon(get_icon("media-playback-pause"))

    def _update_shutdown_button_state(self) -> None:
        q = self._current_queue()

        if not q or q.name == "__direct__" or len(q.downloads) == 0:
            self.shutdown_cb.setEnabled(False)
            if self.shutdown_cb.isChecked():
                self.shutdown_cb.blockSignals(True)
                self.shutdown_cb.setChecked(False)
                self.shutdown_cb.blockSignals(False)
                self.store.settings["shutdown_after_finish"] = False
                self.store.save()
            return

        all_complete = all(
            gid in self._all_downloads
            and self._all_downloads[gid].get("status", "")
            in ["complete", "error", "removed"]
            for gid in q.downloads
        )

        self.shutdown_cb.setEnabled(not all_complete)

    def _update_speed_display(self) -> None:
        total_speed = 0
        has_active = False

        for dl in self._all_downloads.values():
            status = dl.get("status", "")
            if status in ["active", "downloading"]:
                has_active = True
                total_speed += int(dl.get("downloadSpeed", 0))

        self._speed_samples.append(total_speed)
        if len(self._speed_samples) > self._max_samples:
            self._speed_samples.pop(0)

        if self._speed_samples:
            sorted_samples = sorted(self._speed_samples)
            trim = max(1, len(sorted_samples) // 5)
            if len(sorted_samples) > trim * 2:
                samples = sorted_samples[trim:-trim]
            else:
                samples = sorted_samples
            avg_speed = sum(samples) // len(samples)
        else:
            avg_speed = total_speed

        if self._smooth_speed == 0:
            self._smooth_speed = avg_speed
        else:
            self._smooth_speed = int(self._smooth_speed * 0.7 + avg_speed * 0.3)

        speed_text = format_speed(self._smooth_speed)

        if hasattr(self, "speed_status_label"):
            if self.speed_status_label.text() != speed_text:
                self.speed_status_label.setText(speed_text)

        downloading = self._smooth_speed > 0

        if getattr(self, "_last_speed_icon", None) != downloading:
            self._last_speed_icon = downloading
            icon = (
                get_icon("go-down") if downloading else get_icon("media-playback-pause")
            )
            self.speed_icon_label.setPixmap(icon.pixmap(16, 16))

        now = time.monotonic()

        if hasattr(self, "tray") and self.tray.isVisible():
            if has_active and hasattr(self, "tray_icon_active"):
                if self.tray.icon().cacheKey() != self.tray_icon_active.cacheKey():
                    self.tray.setIcon(self.tray_icon_active)
            else:
                if (
                    hasattr(self, "tray_icon_normal")
                    and self.tray.icon().cacheKey() != self.tray_icon_normal.cacheKey()
                ):
                    self.tray.setIcon(self.tray_icon_normal)

            if has_active:
                tooltip = f"FelfelDM - Downloading ({speed_text})"
            else:
                tooltip = "FelfelDM - Ready"

            if now - getattr(
                self, "_last_tooltip_time", 0
            ) >= 1.0 and tooltip != getattr(self, "_last_tooltip", ""):
                self._last_tooltip = tooltip
                self._last_tooltip_time = now
                self.tray.setToolTip(tooltip)
