"""The downloads table: rows, filtering, selection, context menu."""

from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, QPoint, Qt
from PyQt6.QtWidgets import QApplication, QMenu

from utils.helpers import get_icon


class TableViewMixin:
    """The downloads table: rows, filtering, selection, context menu."""

    def _refresh_table(self) -> None:
        q = self._current_queue()
        if not q:
            self._apply_table_rows([])
            return

        rows = []
        search_text = self.search_box.text().strip().lower()

        for download_id in q.downloads:
            if download_id in self._all_downloads:
                row = self._all_downloads[download_id].copy()

            else:
                info = q.downloads_info.get(download_id, {})
                row = {
                    "id": download_id,
                    "aria2_gid": info.get("aria2_gid"),
                    "gid": download_id,
                    "name": info.get("name", "Unknown"),
                    "status": info.get("status", "unknown"),
                    "progress": 0,
                    "downloadSpeed": 0,
                    "totalLength": info.get("totalLength", 0),
                    "completedLength": info.get("completedLength", 0),
                    "category": info.get("category", "📁 Other"),
                    "download_type": info.get("download_type", "normal"),
                    "files": info.get("files", []),
                    "size_fetch_attempts": 0,
                    "error_count": info.get("error_count", 0),
                    "errorMessage": info.get("errorMessage", ""),
                    "matched_rule": info.get("matched_rule"),
                    "rule_speed_limit": info.get("rule_speed_limit", 0),
                    "connections": info.get("connections", 0),
                }
                self._all_downloads[download_id] = row.copy()

            row["sizeUnknown"] = download_id in self._size_unknown

            display_name = row.get("name", "Unknown")
            matched_rule = row.get("matched_rule")
            if matched_rule:
                display_row = row.copy()
                display_row["name"] = f"{display_name}  [rule: {matched_rule}]"
            else:
                display_row = row

            if search_text and search_text not in display_name.lower():
                continue

            rows.append(display_row)

        self._apply_table_rows(rows)

    def _apply_table_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Push new rows into the table model, preserving the selection.

        The table is refreshed several times a second and any model reset
        clears the view's selection, so the selected downloads are captured
        by id and re-selected afterwards. This keeps the selection stable
        across refreshes, row insertions and re-sorting.
        """
        selection = self.table.selectionModel()
        selected_ids: List[str] = []
        if selection is not None:
            for idx in selection.selectedRows():
                gid = self.model.get_gid(idx.row())
                if gid:
                    selected_ids.append(gid)

        self.model.update_rows(rows)

        if not selected_ids or self.table.selectionModel() is None:
            return

        wanted = set(selected_ids)
        new_selection = QItemSelection()
        for row_idx, row in enumerate(self.model.rows):
            row_id = row.get("id") or row.get("gid")
            if row_id in wanted:
                new_selection.select(
                    self.model.index(row_idx, 0),
                    self.model.index(row_idx, self.model.columnCount() - 1),
                )

        if new_selection.isEmpty():
            return

        # Replace the (now empty) selection without emitting a user-edit
        # signal storm; ScrollHint.EnsureVisible keeps the anchor row visible.
        self.table.selectionModel().select(
            new_selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )

    def _filter_downloads(self, text: str) -> None:
        q = self._current_queue()
        if not q:
            self._apply_table_rows([])
            return

        if not text.strip():
            self._refresh_table()
            return

        filtered = []
        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid]
                if text.lower() in row.get("name", "").lower():
                    filtered.append(row)

        self._apply_table_rows(filtered)

    def _selected_gid(self) -> Optional[str]:
        """Return the gid of the selected download, or None.

        Returns None when zero or more than one row is selected, so
        the Details Panel and per-download actions never operate on
        an ambiguous selection.
        """
        if not self.table.selectionModel():
            return None

        rows = self.table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None

        idx = rows[0]
        return self.model.get_gid(idx.row()) if idx.isValid() else None

    def _on_table_double_click(self, index: QModelIndex) -> None:
        gid = self.model.get_gid(index.row())
        if not gid:
            return

        data = self._all_downloads.get(gid, {})
        download_type = data.get("download_type", "normal")

        # Video downloads always open the progress dialog
        if download_type == "video":
            self._open_video_progress_dialog(gid)
            return

        status = data.get("status", "")

        # Completed → open the file directly (Ctrl+Double-Click forces details)
        if status in ("complete", "completed"):
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                self._open_progress_dialog(gid)
                return
            if self._open_download_file(gid):
                return
            # If the file is missing, fall through to the details dialog
            self._open_progress_dialog(gid)
            return

        # Everything else → progress/details dialog
        self._open_progress_dialog(gid)

    def _context_menu(self, pos: QPoint) -> None:
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()

        # No selection: sort-only menu
        if len(rows) == 0:
            menu = QMenu(self)
            menu.addAction(
                "Sort by Name",
                lambda: self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder),
            )
            menu.addAction(
                "Sort by Size",
                lambda: self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Progress",
                lambda: self.table.sortByColumn(2, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Speed",
                lambda: self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Status",
                lambda: self.table.sortByColumn(5, Qt.SortOrder.AscendingOrder),
            )
            menu.addSeparator()
            menu.addAction("Clear Completed", self._clear_completed_downloads)
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        # Multiple selection: bulk menu
        if len(rows) > 1:
            menu = QMenu(self)
            n = len(rows)

            # Gather statuses
            statuses = []
            for r in rows:
                gid = self.model.get_gid(r.row())
                if not gid:
                    continue
                status = self._all_downloads.get(gid, {}).get("status", "")
                if status:
                    statuses.append(status)

            has_active = any(s in ("active", "downloading") for s in statuses)
            has_paused = any(s == "paused" for s in statuses)
            has_error = any(s == "error" for s in statuses)

            if has_active:
                menu.addAction(
                    get_icon("media-playback-pause"),
                    f"Pause {n} downloads",
                    self._pause_selected,
                )
            if has_paused:
                menu.addAction(
                    get_icon("media-playback-start"),
                    f"Resume {n} downloads",
                    self._resume_selected,
                )
            if has_error and n == 1:
                menu.addAction(
                    get_icon("view-refresh"),
                    "Retry",
                    lambda: self._retry_single_download(
                        self.model.get_gid(rows[0].row()), manual=True
                    ),
                )

            menu.addSeparator()
            menu.addAction(
                get_icon("go-next"),
                f"Move {n} to Queue...",
                self._move_selected_to_queue,
            )
            menu.addSeparator()
            menu.addAction(
                get_icon("edit-delete"),
                f"Remove {n} downloads",
                self._remove_selected,
            )
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return
        # Single selection: existing per-download menu
        gid = self.model.get_gid(rows[0].row())
        if not gid:
            return

        dl_data = self._all_downloads.get(gid, {})
        download_type = dl_data.get("download_type", "normal")
        real_status = dl_data.get("status", "")

        menu = QMenu(self)

        if real_status in ["active", "waiting", "downloading"]:
            menu.addAction(
                get_icon("media-playback-pause"),
                "Pause",
                lambda: (
                    self._pause_video_download(gid)
                    if download_type == "video"
                    else self._pause_selected()
                ),
            )
        elif real_status == "paused":
            menu.addAction(
                get_icon("media-playback-start"),
                "Resume",
                lambda: (
                    self._resume_video_download(gid)
                    if download_type == "video"
                    else self._resume_selected()
                ),
            )
        elif real_status == "error":
            menu.addAction(
                get_icon("view-refresh"),
                "Retry",
                lambda: self._retry_single_download(gid, manual=True),
            )

        menu.addSeparator()
        menu.addAction(
            get_icon("folder"), "Open Folder", lambda: self._open_folder(gid)
        )
        menu.addAction(get_icon("edit-copy"), "Copy URL", lambda: self._copy_link(gid))
        menu.addSeparator()
        menu.addAction(get_icon("edit-delete"), "Remove", self._remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))
