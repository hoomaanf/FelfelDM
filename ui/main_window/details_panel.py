"""The details panel under the table."""

import os

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.error_classifier import summarize_detailed
from utils.helpers import format_size, get_icon


class DetailsPanelMixin:
    """The details panel under the table."""

    def _build_details_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("details_panel")
        panel.setMinimumHeight(100)
        panel.setMaximumHeight(190)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(panel)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(16)

        # ── Empty-state label (shown when nothing is selected) ───────────
        self.empty_label = QLabel("Select a download to view details")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("details_empty")
        self.empty_label.setVisible(True)
        lay.addWidget(self.empty_label)

        # ── Details container ───────────────────────────────────────────
        self.details_container = QWidget()
        self.details_container.setVisible(False)
        details_lay = QHBoxLayout(self.details_container)
        details_lay.setContentsMargins(0, 0, 0, 0)
        details_lay.setSpacing(16)

        # ─────────────────────────────────────────────────────────────
        # Left column: download info (card) — takes most of the width
        # ─────────────────────────────────────────────────────────────
        self.info_card = QFrame()
        self.info_card.setObjectName("details_card")
        self.info_card.setFrameShape(QFrame.Shape.NoFrame)

        card_lay = QVBoxLayout(self.info_card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(8)

        info_grid = QGridLayout()
        info_grid.setSpacing(8)
        info_grid.setHorizontalSpacing(14)
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setColumnStretch(0, 0)  # icon
        info_grid.setColumnStretch(1, 0)  # label
        info_grid.setColumnStretch(2, 1)  # value

        # Icon name candidates: first themed icon that resolves wins.
        rows = [
            ("File", "name", ["text-x-generic", "document-new"]),
            ("Size", "size", ["drive-harddisk", "drive-harddisk-symbolic"]),
            ("Downloaded", "downloaded", ["download", "go-bottom", "arrow-down"]),
            ("Status", "status", ["dialog-information", "emblem-info"]),
            ("Path", "path", ["folder", "folder-open"]),
            ("Reason", "reason", ["dialog-warning", "emblem-warning"]),
        ]

        self.detail_labels = {}
        self.detail_icon_labels = {}

        for row_idx, (label_text, key, icon_candidates) in enumerate(rows):
            # -- icon --
            icon_label = QLabel()
            icon_label.setFixedSize(20, 20)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = self._resolve_theme_icon(icon_candidates)
            if icon is not None:
                icon_label.setPixmap(icon.pixmap(18, 18))
            else:
                icon_label.setText("•")
                icon_label.setStyleSheet("color: palette(mid); font-size: 18px;")
            info_grid.addWidget(
                icon_label, row_idx, 0, alignment=Qt.AlignmentFlag.AlignVCenter
            )
            self.detail_icon_labels[key] = icon_label

            # -- label (bolder, slightly larger) --
            lbl = QLabel(f"{label_text}:")
            lbl.setProperty("role", "muted")
            lbl.setMinimumWidth(96)
            info_grid.addWidget(
                lbl, row_idx, 1, alignment=Qt.AlignmentFlag.AlignVCenter
            )

            # -- value (larger, selectable) --
            val = QLabel("—")
            val.setObjectName(f"detail_{key}")
            val.setProperty("role", "value")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(False)
            info_grid.addWidget(
                val, row_idx, 2, alignment=Qt.AlignmentFlag.AlignVCenter
            )
            self.detail_labels[key] = val

        card_lay.addLayout(info_grid)
        card_lay.addStretch()

        # Give the info card much more room than the action column.
        details_lay.addWidget(self.info_card, stretch=5)

        # ─────────────────────────────────────────────────────────────
        # Right column: compact action buttons (single column, small)
        # ─────────────────────────────────────────────────────────────
        action_widget = QWidget()
        action_lay = QVBoxLayout(action_widget)
        action_lay.setSpacing(6)
        action_lay.setContentsMargins(0, 0, 0, 0)

        def _mk_action(icon_name, text, slot):
            btn = QPushButton(get_icon(icon_name), text)
            btn.clicked.connect(slot)
            btn.setMinimumHeight(30)
            btn.setMaximumHeight(30)
            btn.setMinimumWidth(120)
            btn.setMaximumWidth(120)
            btn.setIconSize(QSize(14, 14))
            btn.setEnabled(False)
            btn.setProperty("compact", "true")
            return btn

        self.detail_pause_btn = _mk_action(
            "media-playback-pause", "Pause", self._toggle_pause_resume
        )
        action_lay.addWidget(self.detail_pause_btn)

        self.detail_cancel_btn = _mk_action(
            "edit-delete", "Cancel", self._remove_selected
        )
        self.detail_cancel_btn.setProperty("variant", "danger")
        action_lay.addWidget(self.detail_cancel_btn)

        self.detail_open_btn = _mk_action(
            "folder",
            "Open Folder",
            lambda: self._open_folder(self._selected_gid()),
        )
        action_lay.addWidget(self.detail_open_btn)

        self.detail_copy_btn = _mk_action(
            "edit-copy",
            "Copy URL",
            lambda: self._copy_link(self._selected_gid()),
        )
        action_lay.addWidget(self.detail_copy_btn)

        action_lay.addStretch()

        # Give the action column just enough room — no more.
        details_lay.addWidget(action_widget, stretch=0)

        lay.addWidget(self.details_container)
        return panel

    def _toggle_details_panel(self, checked: bool = False) -> None:
        """Toggle details panel visibility"""
        if not hasattr(self, "details_panel") or self.details_panel is None:
            return

        self._details_visible = not self._details_visible
        self.details_panel.setVisible(self._details_visible)

        if hasattr(self, "btn_show_details"):

            self.btn_show_details.blockSignals(True)
            self.btn_show_details.setChecked(self._details_visible)
            self.btn_show_details.blockSignals(False)

        if self._details_visible:
            self._update_details_panel()

    def _show_details_empty(self, message: str) -> None:
        """Show the empty label with a custom message and hide the details container."""
        if hasattr(self, "empty_label"):
            self.empty_label.setText(message)
            self.empty_label.setVisible(True)
        if hasattr(self, "details_container"):
            self.details_container.setVisible(False)

    def _update_details_panel(self) -> None:
        """Update details panel with selected download info."""
        if not self.table.selectionModel():
            self._show_details_empty("Select a download to view details")
            return

        rows = self.table.selectionModel().selectedRows()

        if len(rows) == 0:
            self._show_details_empty("Select a download to view details")
            return

        if len(rows) > 1:
            self._show_details_empty(
                f"{len(rows)} downloads selected — select a single one for details"
            )
            return

        gid = self.model.get_gid(rows[0].row())
        if not gid or gid not in self._all_downloads:
            self._show_details_empty("Select a download to view details")
            return

        if hasattr(self, "empty_label"):
            self.empty_label.setVisible(False)
        if hasattr(self, "details_container"):
            self.details_container.setVisible(True)

        data = self._all_downloads[gid]

        if hasattr(self, "detail_labels"):

            self.detail_labels["name"].setText(data.get("name", "Unknown"))

            try:
                total = int(data.get("totalLength", 0))
            except (ValueError, TypeError):
                total = 0
            self.detail_labels["size"].setText(format_size(total))

            try:
                downloaded = int(data.get("completedLength", 0))
            except (ValueError, TypeError):
                downloaded = 0
            self.detail_labels["downloaded"].setText(format_size(downloaded))

            status = data.get("status", "unknown")
            status_texts = {
                "active": "Downloading",
                "downloading": "Downloading",
                "waiting": "Waiting",
                "paused": "Paused",
                "complete": "Complete",
                "completed": "Complete",
                "error": "Error",
                "removed": "Removed",
            }
            status_display = status_texts.get(status, status.title())
            self.detail_labels["status"].setText(status_display)

            status_colors = {
                "active": "#27ae60",
                "downloading": "#27ae60",
                "waiting": "#f39c12",
                "paused": "#f39c12",
                "complete": "#3498db",
                "completed": "#3498db",
                "error": "#e74c3c",
            }
            color = status_colors.get(status, "#888")
            self.detail_labels["status"].setStyleSheet(
                f"font-size: 12px; color: {color};"
            )

            from utils.helpers import get_error_reason

            if status in ("error", "retrying"):
                _hist = data.get("error_history") or []
                _detailed = summarize_detailed(_hist)
                if _detailed:
                    # The details panel label is single-line; flatten
                    # the multi-line summary into " | " separators.
                    reason_text = _detailed.replace("\n    last: ", " | ").replace(
                        "\n", " | "
                    )
                else:
                    reason_text = get_error_reason(data.get("errorMessage", ""))
            else:
                reason_text = "—"

            self.detail_labels["reason"].setText(reason_text)
            if status == "error":
                self.detail_labels["reason"].setStyleSheet(
                    "font-size: 12px; color: #e74c3c;"
                )
            elif status == "retrying":
                self.detail_labels["reason"].setStyleSheet(
                    "font-size: 12px; color: #f39c12;"
                )
            else:
                self.detail_labels["reason"].setStyleSheet("font-size: 12px;")

            files = data.get("files", [])
            if files and files[0].get("path"):
                path = os.path.dirname(files[0]["path"])
                self.detail_labels["path"].setText(path)
            else:
                self.detail_labels["path"].setText("—")

        if hasattr(self, "detail_pause_btn"):
            real_status = data.get("status", "")
            download_type = data.get("download_type", "normal")

            if real_status in ["active", "waiting", "downloading"]:
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Pause")
                self.detail_pause_btn.setIcon(get_icon("media-playback-pause"))
            elif real_status == "paused":
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Resume")
                self.detail_pause_btn.setIcon(get_icon("media-playback-start"))
            elif real_status == "error":
                # Errored downloads can be retried (which re-adds them
                # with a fresh gid), even if they're marked permanent.
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Retry")
                self.detail_pause_btn.setIcon(get_icon("view-refresh"))
            elif real_status == "retrying":
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Retrying...")
                self.detail_pause_btn.setIcon(get_icon("view-refresh"))
            elif real_status in ("complete", "completed"):
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Completed")
                self.detail_pause_btn.setIcon(get_icon("emblem-default"))
            else:
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Pause")
                self.detail_pause_btn.setIcon(get_icon("media-playback-pause"))

        if hasattr(self, "detail_cancel_btn"):
            real_status = data.get("status", "")
            # Cancel is available for anything that isn't already
            # complete/retrying — a retrying download is already being
            # handled by the retry logic.
            if real_status in [
                "active",
                "waiting",
                "downloading",
                "paused",
                "error",
            ]:
                self.detail_cancel_btn.setEnabled(True)
            else:
                self.detail_cancel_btn.setEnabled(False)

        if hasattr(self, "detail_open_btn"):
            # Only enable "Open Folder" if the download started (some
            # bytes downloaded or file exists on disk).
            completed = self._to_int(data.get("completedLength", 0))
            self.detail_open_btn.setEnabled(completed > 0)
        if hasattr(self, "detail_copy_btn"):
            self.detail_copy_btn.setEnabled(True)

    def _refresh_empty_state(self, *args) -> None:
        """Show a hint over the table while it has no rows."""
        label = getattr(self, "empty_state", None)
        if label is None:
            return
        if self.model.rowCount() > 0:
            label.setVisible(False)
            return
        query = self.search_box.text().strip() if hasattr(self, "search_box") else ""
        if query:
            label.setText(f"No downloads match “{query}”")
        else:
            label.setText(
                "No downloads here yet\n\n"
                "Press Ctrl+N to add one, or drop a link onto this window"
            )
        label.setVisible(True)
