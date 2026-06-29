# =============================================================================
# ui/table_model.py
# =============================================================================
from typing import Optional, Dict, Any

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex

from core.worker import BackendWorker
from core.queue_model import Queue, DownloadStatus


class DownloadTableModel(QAbstractTableModel):
    """Table model for displaying downloads from the worker's cache."""

    COLUMNS = ["Name", "Size", "Progress", "Speed", "Status", "GID"]

    def __init__(self, worker: BackendWorker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._downloads: Dict[str, Dict[str, Any]] = {}  # gid -> download info
        self._gid_list: list = []

        # Connect to worker's stats update to refresh
        self._worker.stats_updated.connect(self.on_stats_updated)

    def on_stats_updated(self, stats: dict) -> None:
        """Update the model when new stats arrive."""
        # In a real implementation, we would parse the stats to extract downloads.
        # For this example, we assume stats contains a list of active downloads.
        # We'll simulate by using the worker's cached stats.
        self.refresh()

    def refresh(self) -> None:
        """Refresh the model data from the worker's cached stats."""
        stats = self._worker.get_cached_stats()
        # Assume stats is a dict with 'numActive', etc. Actually we need to get list of downloads.
        # To keep it simple, we'll just emit layoutChanged to force refresh.
        # In a full implementation, we would call aria2.tellActive, etc., but we rely on worker.
        # The worker could provide a method to get all downloads.
        # Here we'll just update from a hypothetical list.
        # Since we don't have the exact structure, we'll emit layoutChanged.
        self.layoutChanged.emit()

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
                return download.get("size", "0 B")
            elif col == 2:
                return download.get("progress", "0%")
            elif col == 3:
                return download.get("speed", "0 B/s")
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

    # Additional methods to add/remove downloads can be implemented.
