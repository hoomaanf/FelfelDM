# ui/table_model.py
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor

from utils.helpers import format_eta, format_size, format_speed


class DownloadTableModel(QAbstractTableModel):
    """Table model for download list without GID column visible."""

    COLS = ["Name", "Size", "Progress", "Speed", "ETA", "Status", "Category"]
    GID_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[Dict] = []
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.COLS)

    def headerData(self, section: int, orientation: Qt.Orientation,
                   role: int = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.COLS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self.rows):
            return None

        row = self.rows[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return row.get("name", "—")
            if col == 1:
                t = self._safe_int(row.get("totalLength", 0))
                if t == 0:
                    status = row.get("status", "")
                    if status in ("waiting", "active"):
                        return "⏳ Getting size..."
                return format_size(t) if t > 0 else "—"
            if col == 2:
                t = self._safe_int(row.get("totalLength", 0))
                c = self._safe_int(row.get("completedLength", 0))
                return f"{100 * c // t}%" if t > 0 else "0%"
            if col == 3:
                speed = self._safe_int(row.get("downloadSpeed", 0))
                return format_speed(speed) if speed > 0 else "0 B/s"
            if col == 4:
                total = self._safe_int(row.get("totalLength", 0))
                completed = self._safe_int(row.get("completedLength", 0))
                speed = self._safe_int(row.get("downloadSpeed", 0))
                return format_eta(total, completed, speed)
            if col == 5:
                status = row.get("status", "—")
                status_map = {
                    "active": "⬇ Downloading",
                    "waiting": "⏳ Waiting",
                    "paused": "⏸ Paused",
                    "complete": "✅ Complete",
                    "error": "❌ Error",
                    "removed": " Removed"
                }
                return status_map.get(status, status)
            if col == 6:
                return row.get("category", " Other")

        if role == Qt.ItemDataRole.ForegroundRole and col == 5:
            status = row.get("status", "")
            if status == "complete":
                return QColor("#27ae60")
            if status == "error":
                return QColor("#e74c3c")
            if status == "active":
                return QColor("#3daee9")
            if status == "paused":
                return QColor("#f39c12")
            if status == "waiting":
                return QColor("#95a5a6")

        if role == self.GID_ROLE:
            return row.get("gid")

        return None

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to int, handling None, TypeError and ValueError."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def update_rows(self, new_rows: List[Dict]) -> None:
        """Update table data efficiently."""
        if len(self.rows) == 0 and len(new_rows) == 0:
            return

        if len(self.rows) != len(new_rows):
            self.beginResetModel()
            self.rows = new_rows
            self.endResetModel()
        else:
            self.rows = new_rows
            if len(self.rows) > 0:
                top_left = self.index(0, 0)
                bottom_right = self.index(len(self.rows) - 1, len(self.COLS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
