# =============================================================================
# ui/table_model.py
# =============================================================================
import logging
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex

from core.worker import BackendWorker
from utils.helpers import format_size, format_speed

logger = logging.getLogger(__name__)


class DownloadTableModel(QAbstractTableModel):
    """Table model for displaying downloads using cached data from worker."""

    COLUMNS = ["Name", "Size", "Progress", "Speed", "Status", "GID"]

    def __init__(self, worker: BackendWorker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._downloads: Dict[str, Dict[str, Any]] = {}
        self._gid_list: List[str] = []

        # Connect to worker's downloads_updated signal
        self._worker.downloads_updated.connect(self._on_downloads_updated)

    def _on_downloads_updated(self, download_list: List[Dict[str, Any]]) -> None:
        """Process the list of download dicts and update the model."""
        if not download_list:
            # If list is empty, clear the model
            self._downloads = {}
            self._gid_list = []
            self.layoutChanged.emit()
            return

        new_downloads: Dict[str, Dict[str, Any]] = {}
        for item in download_list:
            gid = item.get("gid")
            if not gid:
                continue
            # Extract name from bittorrent info or use gid
            name = "Unknown"
            if "bittorrent" in item and "info" in item["bittorrent"]:
                name = item["bittorrent"]["info"].get("name", gid)
            elif "files" in item and item["files"]:
                name = item["files"][0].get("path", gid)
            else:
                name = gid

            completed = int(item.get("completedLength", 0))
            total = int(item.get("totalLength", 0))
            progress = (completed / total * 100) if total > 0 else 0
            speed = int(item.get("downloadSpeed", 0))
            status = item.get("status", "unknown")

            new_downloads[gid] = {
                "name": name,
                "size": total,
                "progress": progress,
                "speed": speed,
                "status": status,
                "gid": gid,
            }

        # Update model
        self._downloads = new_downloads
        self._gid_list = list(new_downloads.keys())
        self.layoutChanged.emit()

    def refresh(self) -> None:
        """Refresh the model using the cached downloads from worker."""
        cached = self._worker.get_cached_downloads()
        self._on_downloads_updated(cached)

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._gid_list)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        if row < 0 or row >= len(self._gid_list):
            return None
        gid = self._gid_list[row]
        download = self._downloads.get(gid)
        if not download:
            return None
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return download.get("name", "Unknown")
            elif col == 1:
                return format_size(download.get("size", 0))
            elif col == 2:
                return f"{download.get('progress', 0):.1f}%"
            elif col == 3:
                return format_speed(download.get("speed", 0))
            elif col == 4:
                return download.get("status", "Unknown")
            elif col == 5:
                return gid
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    # Methods to add/update downloads manually (if needed)
    def add_download(self, gid: str, info: Dict[str, Any]) -> None:
        if gid not in self._downloads:
            self._downloads[gid] = info
            self._gid_list.append(gid)
            self.layoutChanged.emit()

    def update_download(self, gid: str, info: Dict[str, Any]) -> None:
        if gid in self._downloads:
            self._downloads[gid].update(info)
            row = self._gid_list.index(gid)
            self.dataChanged.emit(self.index(row, 0), self.index(row, len(self.COLUMNS)-1))
        else:
            self.add_download(gid, info)

    def remove_download(self, gid: str) -> None:
        if gid in self._downloads:
            row = self._gid_list.index(gid)
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._downloads[gid]
            self._gid_list.remove(gid)
            self.endRemoveRows()
