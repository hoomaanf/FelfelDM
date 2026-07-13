from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor
from utils.helpers import (
    format_size,
    format_speed,
    format_eta,
    get_category_from_filename,
)


class DownloadTableModel(QAbstractTableModel):
    COLS = ["Name", "Size", "Progress", "Speed", "ETA", "Status", "Category"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder

    def rowCount(self, p=QModelIndex()):
        return len(self.rows)

    def columnCount(self, p=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, r=Qt.ItemDataRole.DisplayRole):
        if r == Qt.ItemDataRole.DisplayRole and o == Qt.Orientation.Horizontal:
            return self.COLS[s]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None

        row = self.rows[index.row()]
        col = index.column()

        download_type = row.get("download_type", "normal")
        status = row.get("status", "—")

        if isinstance(status, dict):
            status = str(status)
        if not isinstance(status, str):
            status = str(status)

        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:  # Name
                name = row.get("name", "—")
                if download_type == "youtube":
                    yt_title = row.get("yt_options", {}).get("title", "")
                    if yt_title:
                        return yt_title
                if isinstance(name, dict):
                    name = str(name)
                return name

            if col == 1:  # Size
                total = row.get("totalLength", 0)
                if isinstance(total, dict):
                    total = 0
                try:
                    total = int(total)
                except (ValueError, TypeError):
                    total = 0

                if total == 0:
                    if download_type == "youtube" and status in ["downloading", "pending", "paused"]:
                        return "⏳ Getting size..."
                    if status in ["waiting", "active", "paused"]:
                        return "⏳ Getting size..."
                return format_size(total) if total > 0 else "—"

            if col == 2:  # Progress
                total = row.get("totalLength", 0)
                completed = row.get("completedLength", 0)

                if isinstance(total, dict):
                    total = 0
                if isinstance(completed, dict):
                    completed = 0
                try:
                    total = int(total)
                    completed = int(completed)
                except (ValueError, TypeError):
                    total = 0
                    completed = 0

                if download_type == "youtube":
                    progress = row.get("progress", 0)
                    if isinstance(progress, dict):
                        progress = 0
                    try:
                        progress = int(progress)
                    except (ValueError, TypeError):
                        progress = 0
                    return f"{progress}%"

                if total > 0:
                    pct = int((completed / total) * 100)
                    return f"{pct}%"
                return "0%"

            if col == 3:  # Speed
                speed = row.get("downloadSpeed", 0)
                if isinstance(speed, dict):
                    speed = 0
                try:
                    speed = int(speed)
                except (ValueError, TypeError):
                    speed = 0

                if download_type == "youtube":
                    speed_str = row.get("speed", "")
                    if speed_str and isinstance(speed_str, str):
                        return speed_str
                    elif speed_str:
                        return str(speed_str)

                return format_speed(speed) if speed > 0 else "0 B/s"

            if col == 4:  # ETA
                if download_type == "youtube":
                    eta = row.get("eta", "")
                    if eta and isinstance(eta, str):
                        return eta
                    elif eta:
                        return str(eta)
                    return "—"

                total = row.get("totalLength", 0)
                completed = row.get("completedLength", 0)
                speed = row.get("downloadSpeed", 0)

                if isinstance(total, dict):
                    total = 0
                if isinstance(completed, dict):
                    completed = 0
                if isinstance(speed, dict):
                    speed = 0

                try:
                    total = int(total)
                    completed = int(completed)
                    speed = int(speed)
                except (ValueError, TypeError):
                    total = 0
                    completed = 0
                    speed = 0

                return format_eta(total, completed, speed)

            if col == 5:  # Status
                status_map = {
                    "active": "⬇ Downloading",
                    "waiting": "⏳ Waiting",
                    "paused": "⏸ Paused",
                    "complete": "✅ Complete",
                    "completed": "✅ Complete",
                    "error": "❌ Error",
                    "removed": "🗑 Removed",
                    "pending": "⏳ Pending",
                    "downloading": "⬇ Downloading",
                    "cancelled": "🗑 Cancelled",
                }

                if download_type == "youtube":
                    if status == "downloading":
                        return "⬇ Downloading (yt-dlp)"
                    elif status == "pending":
                        return "⏳ Pending"
                    elif status == "paused":
                        return "⏸ Paused"
                    elif status == "completed":
                        return "✅ Complete"
                    elif status == "error":
                        return "❌ Error"

                if not isinstance(status, str):
                    status = str(status)

                result = status_map.get(status)
                if result is None:
                    try:
                        result = status.capitalize()
                    except AttributeError:
                        result = str(status)

                return result

            if col == 6:  # Category
                category = row.get("category", "📁 Other")

                if isinstance(category, dict):
                    category = str(category)
                if not isinstance(category, str):
                    category = str(category)

                if download_type == "youtube":
                    return "🎬 YouTube"

                if category == "📁 Other" or category == "" or category is None:
                    name = row.get("name", "")
                    if isinstance(name, dict):
                        name = str(name)
                    if name:
                        category = get_category_from_filename(name)
                return category

        if role == Qt.ItemDataRole.ToolTipRole and col == 2:
            total = row.get("totalLength", 0)
            completed = row.get("completedLength", 0)

            if isinstance(total, dict):
                total = 0
            if isinstance(completed, dict):
                completed = 0
            try:
                total = int(total)
                completed = int(completed)
            except (ValueError, TypeError):
                total = 0
                completed = 0

            if download_type == "youtube":
                progress = row.get("progress", 0)
                if isinstance(progress, dict):
                    progress = 0
                try:
                    progress = int(progress)
                except (ValueError, TypeError):
                    progress = 0

                speed = row.get("speed", "")
                eta = row.get("eta", "")
                status = row.get("status", "")
                if isinstance(status, dict):
                    status = str(status)

                if status == "completed":
                    return "✅ Download completed!"
                elif status == "downloading":
                    return f"Downloading...\nProgress: {progress}%\nSpeed: {speed}\nETA: {eta}"
                elif status == "paused":
                    return f"⏸ Paused at {progress}%"
                else:
                    return f"Status: {status}\nProgress: {progress}%"

            if total > 0:
                pct = int((completed / total) * 100)
                return f"Downloaded: {format_size(completed)}\nTotal: {format_size(total)}\n{pct}% completed"
            else:
                return "Getting size from server..."

        if role == Qt.ItemDataRole.ForegroundRole and col == 5:
            status = row.get("status", "")
            if isinstance(status, dict):
                status = str(status)
            if not isinstance(status, str):
                status = str(status)

            if download_type == "youtube":
                if status == "completed":
                    return QColor("#27ae60")
                if status == "error":
                    return QColor("#e74c3c")
                if status == "downloading":
                    return QColor("#9b59b6")  
                if status == "paused":
                    return QColor("#f39c12")
                if status == "pending":
                    return QColor("#3498db")

            if status == "complete" or status == "completed":
                return QColor("#27ae60")
            if status == "error":
                return QColor("#e74c3c")
            if status == "active" or status == "downloading":
                return QColor("#3daee9")
            if status == "paused":
                return QColor("#f39c12")
            if status == "waiting" or status == "pending":
                return QColor("#95a5a6")

        if role == Qt.ItemDataRole.BackgroundRole:
            if download_type == "youtube":
                return QColor(155, 89, 182, 20) 

        return None

    def update_rows(self, new_rows):
        if len(self.rows) == 0 and len(new_rows) == 0:
            return

        sort_col = self.sort_column
        sort_order = self.sort_order

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

        if sort_col >= 0:
            self.sort(sort_col, sort_order)

    def get_gid(self, row_idx):
        return self.rows[row_idx].get("gid") if 0 <= row_idx < len(self.rows) else None

    def get_download_type(self, row_idx):
        """دریافت نوع دانلود (normal یا youtube)"""
        if 0 <= row_idx < len(self.rows):
            return self.rows[row_idx].get("download_type", "normal")
        return "normal"

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self.COLS):
            return

        self.sort_column = column
        self.sort_order = order

        sort_keys = {
            0: lambda x: x.get("name", "").lower(),  # Name
            1: lambda x: int(x.get("totalLength", 0)),  # Size
            2: lambda x: self._get_progress_value(x),  # Progress
            3: lambda x: int(x.get("downloadSpeed", 0)),  # Speed
            4: lambda x: self._get_eta_value(x),  # ETA
            5: lambda x: x.get("status", ""),  # Status
            6: lambda x: x.get("category", ""),  # Category
        }

        key_func = sort_keys.get(column, lambda x: x.get("name", "").lower())
        self.rows.sort(key=key_func, reverse=(order == Qt.SortOrder.DescendingOrder))

        self.dataChanged.emit(
            self.index(0, 0), self.index(max(0, len(self.rows) - 1), len(self.COLS) - 1)
        )
        self.layoutChanged.emit()

    def _get_progress_value(self, row):
        total = row.get("totalLength", 0)
        completed = row.get("completedLength", 0)

        if isinstance(total, dict):
            total = 0
        if isinstance(completed, dict):
            completed = 0
        try:
            total = int(total)
            completed = int(completed)
        except (ValueError, TypeError):
            total = 0
            completed = 0

        if row.get("download_type") == "youtube":
            progress = row.get("progress", 0)
            if isinstance(progress, dict):
                progress = 0
            try:
                progress = int(progress)
            except (ValueError, TypeError):
                progress = 0
            return progress

        if total > 0:
            return (completed / total) * 100
        return 0

    def _get_eta_value(self, row):
        total = row.get("totalLength", 0)
        completed = row.get("completedLength", 0)
        speed = row.get("downloadSpeed", 0)

        if isinstance(total, dict):
            total = 0
        if isinstance(completed, dict):
            completed = 0
        if isinstance(speed, dict):
            speed = 0
        try:
            total = int(total)
            completed = int(completed)
            speed = int(speed)
        except (ValueError, TypeError):
            total = 0
            completed = 0
            speed = 0

        if row.get("download_type") == "youtube":
            eta = row.get("eta", "")
            if eta and isinstance(eta, str):
                try:
                    if ":" in eta:
                        parts = eta.split(":")
                        if len(parts) == 2:
                            return int(parts[0]) * 60 + int(parts[1])
                        elif len(parts) == 3:
                            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                except:
                    pass
            return 999999999

        if speed > 0:
            remaining = total - completed
            return remaining // speed
        return 999999999