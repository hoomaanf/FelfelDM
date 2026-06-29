# =============================================================================
# ui/table_model.py
# =============================================================================
import asyncio
import logging
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex

from core.worker import BackendWorker

logger = logging.getLogger(__name__)


class DownloadTableModel(QAbstractTableModel):
    """Table model for displaying downloads with live updates from worker."""

    COLUMNS = ["Name", "Size", "Progress", "Speed", "Status", "GID"]

    def __init__(self, worker: BackendWorker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._downloads: Dict[str, Dict[str, Any]] = {}
        self._gid_list: List[str] = []

        # Connect to worker's stats update
        self._worker.stats_updated.connect(self._on_stats_updated)

    def _on_stats_updated(self, stats: dict) -> None:
        """Fetch download list from aria2 and update model."""
        # Fetch active, waiting, stopped downloads asynchronously
        # Since we are in the UI thread, we run a new event loop to get the data.
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            active = loop.run_until_complete(self._worker.async_aria2.tell_active()) or []
            waiting = loop.run_until_complete(self._worker.async_aria2.tell_waiting(0, 100)) or []
            stopped = loop.run_until_complete(self._worker.async_aria2.tell_stopped(0, 100)) or []
            loop.close()

            all_downloads = active + waiting + stopped

            # Update internal data
            new_downloads: Dict[str, Dict[str, Any]] = {}
            for item in all_downloads:
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

        except Exception as e:
            logger.error("Failed to update download list: %s", e)

    def refresh(self) -> None:
        """Manually refresh the model."""
        self._on_stats_updated({})

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
                from utils.helpers import format_size
                return format_size(download.get("size", 0))
            elif col == 2:
                return f"{download.get('progress', 0):.1f}%"
            elif col == 3:
                from utils.helpers import format_speed
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

    # Methods to add/update downloads (for manual use if needed)
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
