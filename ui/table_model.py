from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor
from utils.helpers import (
    format_size,
    format_speed,
    format_eta,
    get_category_from_filename,
)


class DownloadTableModel(QAbstractTableModel):
    # Column order matters — indices are used all over data() and sort().
    # Name | Size | Progress | Speed | Conns | ETA | Status | Category
    COL_NAME = 0
    COL_SIZE = 1
    COL_PROGRESS = 2
    COL_SPEED = 3
    COL_CONNS = 4
    COL_ETA = 5
    COL_STATUS = 6
    COL_CATEGORY = 7

    COLS = [
        "Name",
        "Size",
        "Progress",
        "Speed",
        "Conns",
        "ETA",
        "Status",
        "Category",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.sort_column = -1
        self.sort_order = Qt.SortOrder.AscendingOrder

    # ─────────────────────────────────────────────────────────────
    # Qt model interface
    # ─────────────────────────────────────────────────────────────

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

        # ── Text alignment ──
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_NAME:
                return int(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            return int(Qt.AlignmentFlag.AlignCenter)

        download_type = row.get("download_type", "normal")
        status = row.get("status", "—")
        if isinstance(status, dict):
            status = str(status)
        if not isinstance(status, str):
            status = str(status)

        # ── Display role ──
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_NAME:
                return self._display_name(row, download_type)

            if col == self.COL_SIZE:
                return self._display_size(row, download_type, status)

            if col == self.COL_PROGRESS:
                return self._display_progress(row, download_type)

            if col == self.COL_SPEED:
                return self._display_speed(row, download_type, status)

            if col == self.COL_CONNS:
                return self._display_connections(row, download_type, status)

            if col == self.COL_ETA:
                return self._display_eta(row, download_type, status)

            if col == self.COL_STATUS:
                return self._display_status(row, download_type, status)

            if col == self.COL_CATEGORY:
                return self._display_category(row, download_type)

        # ── Tooltip ──
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == self.COL_PROGRESS:
                return self._tooltip_progress(row, download_type)
            if col == self.COL_CONNS:
                return self._tooltip_connections(row)

        # ── Foreground (only Status is colored) ──
        if role == Qt.ItemDataRole.ForegroundRole and col == self.COL_STATUS:
            return self._foreground_status(row, download_type, status)

        # ── Background (subtle highlight for YouTube rows) ──
        if role == Qt.ItemDataRole.BackgroundRole:
            if download_type == "youtube":
                return QColor(155, 89, 182, 20)

        return None

    # ─────────────────────────────────────────────────────────────
    # Column renderers
    # ─────────────────────────────────────────────────────────────

    def _display_name(self, row, download_type):
        name = row.get("name", "—")
        if download_type == "youtube":
            yt_title = row.get("yt_options", {}).get("title", "")
            if yt_title:
                return yt_title
        if isinstance(name, dict):
            name = str(name)
        return name

    def _display_size(self, row, download_type, status):
        total = self._to_int(row.get("totalLength", 0))

        if total == 0:
            if download_type == "youtube" and status in (
                "downloading",
                "pending",
                "paused",
            ):
                return "⏳ Getting size..."
            if status in ("waiting", "active", "paused"):
                return "⏳ Getting size..."
            return "—"

        return format_size(total)

    def _display_progress(self, row, download_type):
        if download_type == "youtube":
            progress = self._to_int(row.get("progress", 0))
            return f"{progress}%"

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))

        if total > 0:
            return f"{int((completed / total) * 100)}%"
        return "0%"

    def _display_speed(self, row, download_type, status):
        if status == "paused":
            return "—"

        if download_type == "youtube":
            speed_str = row.get("speed", "")
            if speed_str and isinstance(speed_str, str):
                return speed_str
            if speed_str:
                return str(speed_str)

        speed = self._to_int(row.get("downloadSpeed", 0))
        return format_speed(speed) if speed > 0 else "0 B/s"

    def _display_connections(self, row, download_type, status):
        # No live connections for paused / finished / errored items
        if status in ("paused", "complete", "completed", "error", "removed"):
            return "—"

        if download_type == "youtube":
            return "—"

        conns = self._to_int(row.get("connections", 0))
        return str(conns) if conns > 0 else "—"

    def _display_eta(self, row, download_type, status):
        if status == "paused":
            return "—"

        if download_type == "youtube":
            eta = row.get("eta", "")
            if eta and isinstance(eta, str):
                return eta
            if eta:
                return str(eta)
            return "—"

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))
        speed = self._to_int(row.get("downloadSpeed", 0))
        return format_eta(total, completed, speed)

    def _display_status(self, row, download_type, status):
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
            "stopped": "⏸ Stopped",
            "retrying": "🔄 Retrying...",
        }

        if status == "retrying":
            detail = row.get("status_detail")
            if detail:
                return detail

        if download_type == "youtube":
            yt_map = {
                "downloading": "⬇ Downloading (yt-dlp)",
                "pending": "⏳ Pending",
                "paused": "⏸ Paused",
                "completed": "✅ Complete",
                "error": "❌ Error",
                "cancelled": "🗑 Cancelled",
            }
            if status in yt_map:
                return yt_map[status]

        if not isinstance(status, str):
            status = str(status)

        result = status_map.get(status)
        if result is None:
            try:
                result = status.capitalize()
            except AttributeError:
                result = str(status)
        return result

    def _display_category(self, row, download_type):
        if download_type == "youtube":
            return "🎬 YouTube"

        category = row.get("category", "📁 Other")
        if isinstance(category, dict):
            category = str(category)
        if not isinstance(category, str):
            category = str(category)

        if category in ("📁 Other", "", None):
            name = row.get("name", "")
            if isinstance(name, dict):
                name = str(name)
            if name:
                category = get_category_from_filename(name)
        return category

    # ─────────────────────────────────────────────────────────────
    # Tooltips
    # ─────────────────────────────────────────────────────────────

    def _tooltip_progress(self, row, download_type):
        if download_type == "youtube":
            progress = self._to_int(row.get("progress", 0))
            speed = row.get("speed", "")
            eta = row.get("eta", "")
            status = row.get("status", "")
            if isinstance(status, dict):
                status = str(status)

            if status == "completed":
                return "✅ Download completed!"
            if status == "downloading":
                return (
                    f"Downloading...\nProgress: {progress}%\n"
                    f"Speed: {speed}\nETA: {eta}"
                )
            if status == "paused":
                return f"⏸ Paused at {progress}%"
            return f"Status: {status}\nProgress: {progress}%"

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))

        if total > 0:
            pct = int((completed / total) * 100)
            return (
                f"Downloaded: {format_size(completed)}\n"
                f"Total: {format_size(total)}\n"
                f"{pct}% completed"
            )
        return "Getting size from server..."

    def _tooltip_connections(self, row):
        conns = self._to_int(row.get("connections", 0))
        if conns > 0:
            return f"{conns} active connection(s)"
        return "No active connections"

    # ─────────────────────────────────────────────────────────────
    # Foreground / color
    # ─────────────────────────────────────────────────────────────

    def _foreground_status(self, row, download_type, status):
        if download_type == "youtube":
            yt_colors = {
                "completed": "#27ae60",
                "error": "#e74c3c",
                "downloading": "#9b59b6",
                "paused": "#f39c12",
                "pending": "#3498db",
                "cancelled": "#95a5a6",
            }
            if status in yt_colors:
                return QColor(yt_colors[status])

        colors = {
            "complete": "#27ae60",
            "completed": "#27ae60",
            "error": "#e74c3c",
            "active": "#3daee9",
            "downloading": "#3daee9",
            "paused": "#f39c12",
            "stopped": "#f39c12",
            "waiting": "#95a5a6",
            "pending": "#95a5a6",
            "retrying": "#f39c12",
            "cancelled": "#95a5a6",
        }
        if status in colors:
            return QColor(colors[status])
        return None

    # ─────────────────────────────────────────────────────────────
    # Update / refresh
    # ─────────────────────────────────────────────────────────────

    def update_rows(self, new_rows):
        """Update the model with new runtime data."""
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
                self.dataChanged.emit(
                    top_left,
                    bottom_right,
                    [
                        Qt.ItemDataRole.DisplayRole,
                        Qt.ItemDataRole.ForegroundRole,
                        Qt.ItemDataRole.ToolTipRole,
                        Qt.ItemDataRole.TextAlignmentRole,
                    ],
                )

        if sort_col >= 0:
            self.sort(sort_col, sort_order)

    # ─────────────────────────────────────────────────────────────
    # Accessors
    # ─────────────────────────────────────────────────────────────

    def get_gid(self, row_idx):
        """Get download_id (UUID) from a specific row."""
        if 0 <= row_idx < len(self.rows):
            row = self.rows[row_idx]
            return row.get("id") or row.get("gid")
        return None

    def get_download_type(self, row_idx):
        """Get download type (normal or youtube)."""
        if 0 <= row_idx < len(self.rows):
            return self.rows[row_idx].get("download_type", "normal")
        return "normal"

    # ─────────────────────────────────────────────────────────────
    # Sorting
    # ─────────────────────────────────────────────────────────────

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """Sort rows by the specified column."""
        if column < 0 or column >= len(self.COLS):
            return

        self.sort_column = column
        self.sort_order = order

        sort_keys = {
            self.COL_NAME: lambda x: x.get("name", "").lower(),
            self.COL_SIZE: lambda x: self._to_int(x.get("totalLength", 0)),
            self.COL_PROGRESS: lambda x: self._get_progress_value(x),
            self.COL_SPEED: lambda x: self._to_int(x.get("downloadSpeed", 0)),
            self.COL_CONNS: lambda x: self._to_int(x.get("connections", 0)),
            self.COL_ETA: lambda x: self._get_eta_value(x),
            self.COL_STATUS: lambda x: x.get("status", ""),
            self.COL_CATEGORY: lambda x: x.get("category", ""),
        }

        key_func = sort_keys.get(column, lambda x: x.get("name", "").lower())
        self.rows.sort(key=key_func, reverse=(order == Qt.SortOrder.DescendingOrder))

        self.dataChanged.emit(
            self.index(0, 0),
            self.index(max(0, len(self.rows) - 1), len(self.COLS) - 1),
        )
        self.layoutChanged.emit()

    def _get_progress_value(self, row):
        """Get progress value (0–100) for sorting."""
        if row.get("download_type") == "youtube":
            return self._to_int(row.get("progress", 0))

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))

        if total > 0:
            return (completed / total) * 100
        return 0

    def _get_eta_value(self, row):
        """Get ETA value in seconds for sorting (large = unknown)."""
        if row.get("download_type") == "youtube":
            eta = row.get("eta", "")
            if eta and isinstance(eta, str) and ":" in eta:
                try:
                    parts = eta.split(":")
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(parts[1])
                    if len(parts) == 3:
                        return (
                            int(parts[0]) * 3600
                            + int(parts[1]) * 60
                            + int(parts[2])
                        )
                except Exception:
                    pass
            return 999999999

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))
        speed = self._to_int(row.get("downloadSpeed", 0))

        if speed > 0:
            remaining = total - completed
            return remaining // speed
        return 999999999

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_int(value) -> int:
        if value is None:
            return 0
        if isinstance(value, dict):
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0