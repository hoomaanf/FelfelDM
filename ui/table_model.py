# ui/table_model.py
"""
Table model for download items with GID role and tooltips.
"""

import logging
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, pyqtSignal

from core.data_store import DataStore
from core.enums import DownloadStatus  # ✅ اصلاح شده: از enums import می‌کند
from utils.helpers import format_size, format_speed

logger = logging.getLogger(__name__)


class DownloadTableModel(QAbstractTableModel):
    """
    Table model for displaying downloads.
    """

    COLS = ["Name", "Size", "Progress", "Speed", "ETA", "Status", "Category"]
    GID_ROLE = Qt.ItemDataRole.UserRole + 1

    data_changed = pyqtSignal()

    def __init__(self, store: DataStore, queue_controller) -> None:
        super().__init__()
        self.store = store
        self.queue_controller = queue_controller
        self._downloads: List[Dict[str, Any]] = []
        self._gid_map: Dict[str, int] = {}
        self._cached_stats: Dict[str, Any] = {}

    def refresh(self) -> None:
        """Refresh the table data."""
        self.beginResetModel()
        self._downloads = []
        self._gid_map = {}

        queue = self.queue_controller.get_current_queue()
        if queue:
            for gid in queue.downloads:
                # Get status from cache or fetch
                status = self._cached_stats.get(gid, {})
                self._downloads.append({
                    "gid": gid,
                    "status": status,
                })
                self._gid_map[gid] = len(self._downloads) - 1

        self.endResetModel()

    def update_status(self, gid: str, status: Dict[str, Any]) -> None:
        """Update the status of a specific download."""
        self._cached_stats[gid] = status
        if gid in self._gid_map:
            row = self._gid_map[gid]
            self.dataChanged.emit(
                self.index(row, 0),
                self.index(row, len(self.COLS) - 1)
            )

    def get_gid(self, row: int) -> Optional[str]:
        """Get the GID at the given row."""
        if 0 <= row < len(self._downloads):
            return self._downloads[row].get("gid")
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._downloads)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.COLS[section]
        return None

    def data(self, index: QModelIndex, role: int):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        if row >= len(self._downloads):
            return None

        download = self._downloads[row]
        gid = download.get("gid")
        status = download.get("status", {})

        # Tooltip role - show detailed information
        if role == Qt.ItemDataRole.ToolTipRole:
            if gid:
                tooltip_lines = [
                    f"GID: {gid}",
                    f"Status: {status.get('status', 'Unknown')}",
                ]
                if status.get("downloadSpeed"):
                    tooltip_lines.append(f"Speed: {format_speed(int(status['downloadSpeed']))}")
                if status.get("totalLength"):
                    tooltip_lines.append(f"Size: {format_size(int(status['totalLength']))}")
                if status.get("completedLength"):
                    tooltip_lines.append(f"Downloaded: {format_size(int(status['completedLength']))}")
                if status.get("savePath"):
                    tooltip_lines.append(f"Save Path: {status['savePath']}")
                if status.get("followedBy"):
                    tooltip_lines.append(f"Followed By: {status['followedBy']}")

                return "\n".join(tooltip_lines)
            return None

        # GID role
        if role == self.GID_ROLE:
            return gid

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        # Display data
        if col == 0:  # Name
            name = status.get("name", gid[:8] if gid else "Unknown")
            if not name or name == "":
                name = status.get("bittorrent", {}).get("name", gid[:8] if gid else "Unknown")
            return name

        elif col == 1:  # Size
            size = status.get("totalLength", 0)
            return format_size(int(size)) if size else "—"

        elif col == 2:  # Progress
            total = int(status.get("totalLength", 0))
            completed = int(status.get("completedLength", 0))
            if total > 0:
                return f"{int((completed / total) * 100)}%"
            return "0%"

        elif col == 3:  # Speed
            speed = status.get("downloadSpeed", 0)
            return format_speed(int(speed)) if speed else "—"

        elif col == 4:  # ETA
            total = int(status.get("totalLength", 0))
            completed = int(status.get("completedLength", 0))
            speed = int(status.get("downloadSpeed", 0))
            if total > 0 and speed > 0 and completed < total:
                eta_sec = (total - completed) // speed
                if eta_sec < 60:
                    return f"{eta_sec}s"
                elif eta_sec < 3600:
                    return f"{eta_sec // 60}m {eta_sec % 60}s"
                else:
                    return f"{eta_sec // 3600}h {(eta_sec % 3600) // 60}m"
            return "—"

        elif col == 5:  # Status
            raw_status = status.get("status", "unknown")
            try:
                status_enum = DownloadStatus.from_string(raw_status)
                return status_enum.value
            except ValueError:
                return raw_status.capitalize()

        elif col == 6:  # Category
            name = status.get("name", "")
            if name:
                from utils.helpers import get_category
                return get_category(name)
            return "Other"

        return None
