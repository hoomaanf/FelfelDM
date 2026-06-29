# ui/table_model.py

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor
from utils.helpers import format_size, format_speed, format_eta

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

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        row = self.rows[index.row()]
        col = index.column()
        
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0: return row.get("name", "—")
            if col == 1:
                t = int(row.get("totalLength", 0))
                if t == 0:
                    status = row.get("status", "")
                    # ✅ برای waiting, active و paused هم "⏳ Getting size..." نشون بده
                    if status in ["waiting", "active", "paused"]:
                        return "⏳ Getting size..."
                return format_size(t) if t > 0 else "—"
            if col == 2:
                t = int(row.get("totalLength", 0))
                c = int(row.get("completedLength", 0))
                return f"{100*c//t}%" if t > 0 else "0%"
            if col == 3: 
                speed = row.get("downloadSpeed", 0)
                try:
                    speed = int(speed)
                except (ValueError, TypeError):
                    speed = 0
                return format_speed(speed) if speed > 0 else "0 B/s"
            if col == 4:
                total = int(row.get("totalLength", 0))
                completed = int(row.get("completedLength", 0))
                speed = row.get("downloadSpeed", 0)
                try:
                    speed = int(speed)
                except (ValueError, TypeError):
                    speed = 0
                return format_eta(total, completed, speed)
            if col == 5: 
                status = row.get("status", "—")
                status_map = {
                    "active": "⬇ Downloading",
                    "waiting": "⏳ Waiting",
                    "paused": "⏸ Paused",
                    "complete": "✅ Complete",
                    "error": "❌ Error",
                    "removed": "🗑 Removed"
                }
                return status_map.get(status, status)
            if col == 6: return row.get("category", "📁 Other")
            
        if role == Qt.ItemDataRole.ForegroundRole and col == 5:
            status = row.get("status", "")
            if status == "complete": return QColor("#27ae60")
            if status == "error": return QColor("#e74c3c")
            if status == "active": return QColor("#3daee9")
            if status == "paused": return QColor("#f39c12")
            if status == "waiting": return QColor("#95a5a6")
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

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0 or column >= len(self.COLS):
            return
        
        self.sort_column = column
        self.sort_order = order
        
        sort_keys = {
            0: lambda x: x.get("name", "").lower(),           # Name
            1: lambda x: int(x.get("totalLength", 0)),         # Size
            2: lambda x: self._get_progress_value(x),          # Progress
            3: lambda x: int(x.get("downloadSpeed", 0)),       # Speed
            4: lambda x: self._get_eta_value(x),               # ETA
            5: lambda x: x.get("status", ""),                  # Status
            6: lambda x: x.get("category", ""),                # Category
        }
        
        key_func = sort_keys.get(column, lambda x: x.get("name", "").lower())
        
        self.rows.sort(key=key_func, reverse=(order == Qt.SortOrder.DescendingOrder))
        
        self.dataChanged.emit(self.index(0, 0), self.index(max(0, len(self.rows) - 1), len(self.COLS) - 1))
        self.layoutChanged.emit()
    
    def _get_progress_value(self, row):
        total = int(row.get("totalLength", 0))
        completed = int(row.get("completedLength", 0))
        if total > 0:
            return (completed / total) * 100
        return 0
    
    def _get_eta_value(self, row):
        total = int(row.get("totalLength", 0))
        completed = int(row.get("completedLength", 0))
        speed = int(row.get("downloadSpeed", 0))
        if speed > 0:
            remaining = total - completed
            return remaining // speed
        return 999999999