# =============================================================================
# ui/table_model.py
# =============================================================================
from typing import Optional, Dict, Any

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex, pyqtSignal

from core.worker import BackendWorker


class DownloadTableModel(QAbstractTableModel):
    """Table model for displaying downloads with live updates from worker."""

    COLUMNS = ["Name", "Size", "Progress", "Speed", "Status", "GID"]

    def __init__(self, worker: BackendWorker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._downloads: Dict[str, Dict[str, Any]] = {}  # gid -> download info
        self._gid_list: list = []

        # Connect to worker's stats update
        self._worker.stats_updated.connect(self._on_stats_updated)

    def _on_stats_updated(self, stats: dict) -> None:
        """
        Called when worker receives new stats. Updates internal data and notifies UI.
        The stats parameter is a dict from aria2.getGlobalStat.
        In a complete implementation, we would also call tellActive, tellWaiting, etc.
        For now, we simulate with a dummy refresh.
        """
        # In a real app, we'd fetch active downloads via worker's method.
        # Since the worker might not expose detailed download lists directly,
        # we will rely on the worker to emit signals for each download update.
        # For simplicity, we just emit layoutChanged to cause a refresh.
        # This should be replaced with a proper update mechanism in production.
        self.layoutChanged.emit()

    def refresh(self) -> None:
        """Manually refresh the model (delegates to worker's cache)."""
        # The worker will emit stats_updated, which triggers _on_stats_updated.
        # We can call worker's get_cached_stats to get the latest global stats,
        # but we need a mechanism to get the list of downloads.
        # This implementation assumes the worker provides a signal for download list.
        # For now, we just emit layoutChanged.
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

    # Methods to add/update downloads
    def add_download(self, gid: str, info: Dict[str, Any]) -> None:
        if gid not in self._downloads:
            self._downloads[gid] = info
            self._gid_list.append(gid)
            self.layoutChanged.emit()

    def update_download(self, gid: str, info: Dict[str, Any]) -> None:
        if gid in self._downloads:
            self._downloads[gid].update(info)
            # Optionally emit dataChanged for specific row
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
