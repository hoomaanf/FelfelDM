from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor
from utils.style import theme_color
from utils.helpers import (
    format_size,
    format_speed,
    format_eta,
    get_category_from_filename,
    get_icon,
)
from core.error_classifier import summarize, summarize_detailed

# ─────────────────────────────────────────────────────────────────────
# Category → icon-theme name.
# utils/helpers.py still returns emoji-prefixed strings; we translate
# at the display layer only. Comparisons in the rest of the code keep
# working against the emoji-prefixed form.
# ─────────────────────────────────────────────────────────────────────
CATEGORY_ICON_NAMES = {
    "🎬 Video": "video-x-generic",
    "🎵 Audio": "audio-x-generic",
    "📦 Archive": "package-x-generic",
    "📄 Document": "x-office-document",
    "🖼️ Image": "image-x-generic",
    "⚙️ Program": "application-x-executable",
    "💻 Code": "text-x-script",
    "📚 Ebook": "application-epub+zip",
    "🔤 Font": "font-x-generic",
    "🗄️ Database": "application-x-sqlite2",
    "💿 Disk": "drive-harddisk",
    "🧲 Torrent": "application-x-bittorrent",
    "📝 Subtitle": "text-x-generic-template",
    "📋 Playlist": "audio-x-playlist",
    "📁 Other": "folder",
    "🎬 Video": "applications-multimedia",
}

CATEGORY_DISPLAY = {
    "🎬 Video": "Video",
    "🎵 Audio": "Audio",
    "📦 Archive": "Archive",
    "📄 Document": "Document",
    "🖼️ Image": "Image",
    "⚙️ Program": "Program",
    "💻 Code": "Code",
    "📚 Ebook": "Ebook",
    "🔤 Font": "Font",
    "🗄️ Database": "Database",
    "💿 Disk": "Disk",
    "🧲 Torrent": "Torrent",
    "📝 Subtitle": "Subtitle",
    "📋 Playlist": "Playlist",
    "📁 Other": "Other",
    "🎬 Video": "Video",
}

STATUS_ICON_NAMES = {
    "active": "go-down",
    "downloading": "go-down",
    "waiting": "appointment-soon",
    "paused": "media-playback-pause",
    "complete": "emblem-default",
    "completed": "emblem-default",
    "error": "dialog-error",
    "removed": "edit-delete",
    "pending": "appointment-soon",
    "cancelled": "edit-delete",
    "stopped": "media-playback-pause",
    "retrying": "view-refresh",
}

STATUS_DISPLAY = {
    "active": "Downloading",
    "downloading": "Downloading",
    "waiting": "Waiting",
    "paused": "Paused",
    "complete": "Complete",
    "completed": "Complete",
    "error": "Error",
    "removed": "Removed",
    "pending": "Pending",
    "cancelled": "Cancelled",
    "stopped": "Stopped",
    "retrying": "Retrying...",
}


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

    @staticmethod
    def _row_identity(row):
        """Stable identity for a row, used to detect a changed row set.

        Length alone is not enough: filtering can swap every row while the
        count stays the same, and the previous code only emitted
        dataChanged in that case. Any surviving selection or open progress
        dialog would then point at a different download.
        """
        if not isinstance(row, dict):
            return None
        return row.get("id") or row.get("gid")

    # ─────────────────────────────────────────────────────────────
    # Qt model interface
    # ─────────────────────────────────────────────────────────────

    def rowCount(self, p=QModelIndex()):
        return len(self.rows)

    def columnCount(self, p=QModelIndex()):
        return len(self.COLS)

    def headerData(self, s, o, r=Qt.ItemDataRole.DisplayRole):
        if r == Qt.ItemDataRole.TextAlignmentRole and o == Qt.Orientation.Horizontal:
            if s == self.COL_NAME:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignCenter)
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
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
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

        # ── Decoration (icon) role — Category column shows a theme icon ──
        if role == Qt.ItemDataRole.DecorationRole and col == self.COL_CATEGORY:
            return self._category_icon(row, download_type)

        # ── Tooltip ──
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == self.COL_PROGRESS:
                return self._tooltip_progress(row, download_type)
            if col == self.COL_CONNS:
                return self._tooltip_connections(row)
            if col == self.COL_CATEGORY:
                return self._display_category(row, download_type)
            if col == self.COL_STATUS:
                hist = row.get("error_history") or []
                detailed = summarize_detailed(hist)
                if detailed:
                    return detailed

        # ── Foreground (only Status is colored) ──
        if role == Qt.ItemDataRole.ForegroundRole and col == self.COL_STATUS:
            return self._foreground_status(row, download_type, status)

        # ── Background (subtle highlight for Video rows) ──
        if role == Qt.ItemDataRole.BackgroundRole:
            if download_type == "video":
                return QColor(155, 89, 182, 20)

        return None

    # ─────────────────────────────────────────────────────────────
    # Column renderers
    # ─────────────────────────────────────────────────────────────

    def _display_name(self, row, download_type):
        name = row.get("name", "—")
        if download_type == "video":
            yt_title = row.get("yt_options", {}).get("title", "")
            if yt_title:
                return yt_title
        if isinstance(name, dict):
            name = str(name)
        return name

    def _display_size(self, row, download_type, status):
        total = self._to_int(row.get("totalLength", 0))

        if total == 0:
            if row.get("sizeUnknown") and status not in ("complete", "completed"):
                return "Unknown"
            if download_type == "video" and status in (
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
        if download_type == "video":
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

        if download_type == "video":
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

        if download_type == "video":
            return "—"

        conns = self._to_int(row.get("connections", 0))
        return str(conns) if conns > 0 else "—"

    def _display_eta(self, row, download_type, status):
        if status == "paused":
            return "—"

        if download_type == "video":
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
        # Errored downloads show a compact summary of the error history
        # (e.g. "Error: DNS ×3, Timeout ×2"). Falls back to plain "Error"
        # when there is no history yet.
        if status == "error":
            hist = row.get("error_history") or []
            short = summarize(hist)
            return f"Error: {short}" if short else "Error"

        # Retrying has a countdown detail string that replaces the label.
        if status == "retrying":
            detail = row.get("status_detail")
            if detail:
                # Strip any leading emoji like "🔄 " if present.
                return detail.lstrip("🔄 ").strip() or "Retrying..."

        # Video uses a slightly different vocabulary.
        if download_type == "video":
            yt_map = {
                "downloading": "Downloading (yt-dlp)",
                "pending": "Pending",
                "paused": "Paused",
                "completed": "Complete",
                "error": "Error",
                "cancelled": "Cancelled",
            }
            if status in yt_map:
                return yt_map[status]

        if not isinstance(status, str):
            status = str(status)

        status_map = {
            "active": "Downloading",
            "downloading": "Downloading",
            "waiting": "Waiting",
            "paused": "Paused",
            "complete": "Complete",
            "completed": "Complete",
            "error": "Error",
            "removed": "Removed",
            "pending": "Pending",
            "cancelled": "Cancelled",
            "stopped": "Stopped",
            "retrying": "Retrying...",
        }

        result = status_map.get(status)
        if result is None:
            try:
                result = status.capitalize()
            except AttributeError:
                result = str(status)
        return result

    def _display_category(self, row, download_type):
        """Category as plain text (no emoji) — the icon is drawn by
        the DecorationRole branch of data()."""
        if download_type == "video":
            return "Video"

        category = row.get("category", "📁 Other")
        if isinstance(category, dict):
            category = str(category)
        if not isinstance(category, str):
            category = str(category)

        # If the row has no explicit category, derive it from the filename.
        if category in ("📁 Other", "", None):
            name = row.get("name", "")
            if isinstance(name, dict):
                name = str(name)
            if name:
                category = get_category_from_filename(name)

        # Lookup the plain name. Fall back to stripping any leading
        # emoji-run if the key is unknown.
        return CATEGORY_DISPLAY.get(
            category,
            category.lstrip("📁🎬🎵📦📄🖼️⚙️💻📚🔤🗄️💿🧲📝📋 ").strip() or "Other",
        )

    def _category_icon(self, row, download_type):
        """Return a QIcon for the Category column's decoration."""
        if download_type == "video":
            key = "🎬 Video"
        else:
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
            key = category

        icon_name = CATEGORY_ICON_NAMES.get(key, "folder")
        icon = get_icon(icon_name)
        if icon.isNull():
            icon = get_icon("folder")
        return icon

    # ─────────────────────────────────────────────────────────────
    # Tooltips
    # ─────────────────────────────────────────────────────────────

    def _tooltip_progress(self, row, download_type):
        if download_type == "video":
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
        if row.get("sizeUnknown"):
            return "Size unknown: the server did not report it or the fetch failed"
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
        if download_type == "video":
            yt_colors = {
                "completed": "success_text",
                "error": "danger",
                "downloading": "purple",
                "paused": "warning",
                "pending": "accent_text",
                "cancelled": "muted",
            }
            if status in yt_colors:
                return theme_color(yt_colors[status])

        colors = {
            "complete": "success_text",
            "completed": "success_text",
            "error": "danger",
            "active": "accent_text",
            "downloading": "accent_text",
            "paused": "warning",
            "stopped": "warning",
            "waiting": "muted",
            "pending": "muted",
            "retrying": "warning",
            "cancelled": "muted",
        }
        if status in colors:
            return theme_color(colors[status])
        return None

    # ─────────────────────────────────────────────────────────────
    # Update / refresh
    # ─────────────────────────────────────────────────────────────

    def update_rows(self, new_rows):
        """Update the model with new runtime data.

        The steady-state path (a periodic stats refresh where the same
        downloads are present) must emit only dataChanged. Any model reset
        clears the view's selection, and this is called several times a
        second, so resetting here made the table impossible to select from.
        """
        if len(self.rows) == 0 and len(new_rows) == 0:
            return

        # Apply the active sort to the incoming data *before* touching the
        # model, so ordering stays correct without going through sort().
        new_rows = self._sorted_copy(new_rows)

        old_ids = [self._row_identity(r) for r in self.rows]
        new_ids = [self._row_identity(r) for r in new_rows]

        if old_ids != new_ids:
            # A different set of downloads (add/remove/filter/reorder):
            # indexes genuinely change, so a reset is required.
            self.beginResetModel()
            self.rows = new_rows
            self.endResetModel()
            return

        self.rows = new_rows
        if len(self.rows) > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self.rows) - 1, len(self.COLS) - 1)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [
                    Qt.ItemDataRole.DisplayRole,
                    Qt.ItemDataRole.DecorationRole,
                    Qt.ItemDataRole.ForegroundRole,
                    Qt.ItemDataRole.ToolTipRole,
                    Qt.ItemDataRole.TextAlignmentRole,
                ],
            )

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
        """Get download type (normal or video)."""
        if 0 <= row_idx < len(self.rows):
            return self.rows[row_idx].get("download_type", "normal")
        return "normal"

    # ─────────────────────────────────────────────────────────────
    # Sorting
    # ─────────────────────────────────────────────────────────────

    def _sort_key(self, column):
        """Comparison key for one column."""
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
        return sort_keys.get(column, lambda x: x.get("name", "").lower())

    def _sorted_copy(self, rows):
        """Return `rows` ordered by the active sort, without emitting signals."""
        if self.sort_column < 0:
            return list(rows)
        return sorted(
            rows,
            key=self._sort_key(self.sort_column),
            reverse=(self.sort_order == Qt.SortOrder.DescendingOrder),
        )

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        """Re-sort the model (invoked when the user clicks a column header)."""
        if column < 0 or column >= len(self.COLS):
            return

        self.sort_column = column
        self.sort_order = order

        # Reordering invalidates persistent indexes, so tell the view via a
        # reset. This only happens on an explicit user action, where losing
        # the selection is expected; the periodic refresh path does not come
        # through here (see update_rows).
        self.beginResetModel()
        self.rows = self._sorted_copy(self.rows)
        self.endResetModel()

    def _get_progress_value(self, row):
        """Get progress value (0–100) for sorting."""
        if row.get("download_type") == "video":
            return self._to_int(row.get("progress", 0))

        total = self._to_int(row.get("totalLength", 0))
        completed = self._to_int(row.get("completedLength", 0))

        if total > 0:
            return (completed / total) * 100
        return 0

    def _get_eta_value(self, row):
        """Get ETA value in seconds for sorting (large = unknown)."""
        if row.get("download_type") == "video":
            eta = row.get("eta", "")
            if eta and isinstance(eta, str) and ":" in eta:
                try:
                    parts = eta.split(":")
                    if len(parts) == 2:
                        return int(parts[0]) * 60 + int(parts[1])
                    if len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
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
