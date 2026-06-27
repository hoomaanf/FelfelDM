# Requires: PyQt6>=6.4.0

"""
Table model for displaying download information with ETA and speed columns.
"""

import os
from typing import List, Dict, Any, Optional

from PyQt6.QtCore import QAbstractTableModel, Qt, QModelIndex

from core.data_store import DataStore


class DownloadTableModel(QAbstractTableModel):
    """Table model for downloads with ETA and speed."""

    def __init__(self, store: DataStore) -> None:
        super().__init__()
        self.store = store
        self._downloads: List[Dict[str, Any]] = []
        self._headers = [
            "GID",
            "Name",
            "Size",
            "Progress",
            "Status",
            "Speed",
            "ETA",
            "Connections",
            "Queue",
        ]

    def update_downloads(
        self,
        active: List[Dict[str, Any]],
        waiting: List[Dict[str, Any]],
        stopped: List[Dict[str, Any]],
    ) -> None:
        combined = []
        seen = set()
        for dl in active + waiting + stopped:
            gid = dl.get("gid")
            if not gid or gid in seen:
                continue
            seen.add(gid)
            total = int(dl.get("totalLength", 0))
            completed = int(dl.get("completedLength", 0))
            progress = (completed / total * 100) if total > 0 else 0

            name = dl.get("files", [{}])[0].get("path", "Unknown")
            if name and "/" in name:
                name = os.path.basename(name)
            elif not name:
                name = "Unknown"

            status = dl.get("status", "unknown")
            speed = int(dl.get("downloadSpeed", 0))
            connections = int(dl.get("connections", 0))
            eta = int(dl.get("eta", 0))

            # Determine queue from store (if we stored it)
            queue_name = "Default"
            for q in self.store.queues:
                if gid in q.downloads:
                    queue_name = q.name
                    break

            combined.append({
                "gid": gid,
                "name": name,
                "total": total,
                "completed": completed,
                "progress": progress,
                "status": status,
                "speed": speed,
                "connections": connections,
                "eta": eta,
                "queue": queue_name,
                "raw": dl,
            })

        self.beginResetModel()
        self._downloads = combined
        self.endResetModel()

    def refresh(self) -> None:
        pass

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._downloads)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Optional[Any]:
        if not index.isValid() or index.row() >= len(self._downloads):
            return None
        row = index.row()
        col = index.column()
        dl = self._downloads[row]

        if role == Qt.ItemDataRole.UserRole:
            if col == 0:
                return dl.get("gid")
            return None

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return dl.get("gid", "")[:8]
            elif col == 1:
                return dl.get("name", "Unknown")
            elif col == 2:
                total = dl.get("total", 0)
                return self._format_size(total)
            elif col == 3:
                progress = dl.get("progress", 0)
                return f"{progress:.1f}%"
            elif col == 4:
                status = dl.get("status", "unknown")
                return self._translate_status(status)
            elif col == 5:
                speed = dl.get("speed", 0)
                return self._format_speed(speed)
            elif col == 6:
                eta = dl.get("eta", 0)
                if eta > 0:
                    hours = eta // 3600
                    minutes = (eta % 3600) // 60
                    seconds = eta % 60
                    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                return "--"
            elif col == 7:
                return dl.get("connections", 0)
            elif col == 8:
                return dl.get("queue", "Default")
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Optional[str]:
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(self._headers):
                return self._headers[section]
        return None

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    @staticmethod
    def _format_speed(speed: int) -> str:
        if speed == 0:
            return "0 B/s"
        for unit in ['B/s', 'KB/s', 'MB/s', 'GB/s']:
            if speed < 1024.0:
                return f"{speed:.1f} {unit}"
            speed /= 1024.0
        return f"{speed:.1f} TB/s"

    @staticmethod
    def _translate_status(status: str) -> str:
        mapping = {
            "active": "Downloading",
            "waiting": "Waiting",
            "paused": "Paused",
            "error": "Error",
            "complete": "Complete",
            "removed": "Removed",
        }
        return mapping.get(status, status)
