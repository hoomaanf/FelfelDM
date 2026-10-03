import os
import subprocess
import time
import socket

from PyQt6.QtWidgets import *
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
import tempfile
from PyQt6.QtCore import *
from PyQt6.QtCore import QPointF, QRectF

from utils.helpers import get_icon
from utils.helpers import format_size
from core.queue_model import Queue
from datetime import datetime, time as dtime
from core.proxy_manager import ProxyType, ProxyConfig
from core.size_fetcher_worker import SizeFetcherWorker

# ═══════════════════════════════════════════════════════════════════
# Base / reusable widgets
# ═══════════════════════════════════════════════════════════════════


class AccordionGroup(QWidget):
    """Collapsible group with a toggle button header."""

    def __init__(self, title, parent=None, expanded=True):
        super().__init__(parent)
        self._expanded = expanded

        self.toggle_btn = QPushButton()
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-weight: 600;
                padding: 8px 10px;
                border: none;
                border-radius: 4px;
                background: transparent;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.05);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,0.08);
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle)
        self.toggle_btn.setFixedHeight(32)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 5, 10, 10)
        self.content_layout.setSpacing(8)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_btn)

        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.line.setStyleSheet("background-color: #313244; max-height: 1px;")
        main_layout.addWidget(self.line)

        main_layout.addWidget(self.content)

        self.set_title(title)
        self.set_expanded(expanded)

    def set_title(self, title):
        self.toggle_btn.setText(f"  {title}")
        self._update_icon()

    def _update_icon(self):
        icon = get_icon("go-down") if self._expanded else get_icon("go-next")
        self.toggle_btn.setIcon(icon)

    def _toggle(self):
        self.set_expanded(not self._expanded)
        self._update_parent_dialog_size()

    def _update_parent_dialog_size(self):
        try:
            parent = self.window()
            if parent and hasattr(parent, "adjustSize"):
                QTimer.singleShot(50, parent.adjustSize)
        except Exception as e:
            print(f"⚠️ Error updating dialog size: {e}")

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.content.setVisible(expanded)
        self.line.setVisible(expanded)
        self._update_icon()

    def is_expanded(self):
        return self._expanded

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)

    def layout(self):
        return self.content_layout


class _ClickableCheckboxWidget(QWidget):
    """
    Wrapper around a QCheckBox that makes the WHOLE cell clickable.
    Clicking anywhere in the widget toggles the checkbox.
    """

    def __init__(self, checkbox: QCheckBox, parent=None):
        super().__init__(parent)
        self._cb = checkbox

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cb)

        self.mousePressEvent = self._on_mouse_press

    def _on_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._cb.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def is_checked(self) -> bool:
        return self._cb.isChecked()

    def set_checked(self, checked: bool):
        self._cb.setChecked(checked)


def _make_stripe_pixmap(
    stripe_color: str, base_color: str, width: int = 16, height: int = 16
) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(base_color))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.setPen(QPen(QColor(stripe_color), 4, Qt.PenStyle.SolidLine))

    for x in range(-height, width + height, 8):
        painter.drawLine(x, height, x + height, 0)

    painter.end()
    return pixmap


class StripedProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._base_color = "#89b4fa"
        self._stripe_color = "#f9e2af"
        self._striped = False
        self._stripe_pixmap = None
        self._build_pixmap()
        self.setStyleSheet(self._build_style())

    def _build_pixmap(self):
        self._stripe_pixmap = _make_stripe_pixmap(self._stripe_color, self._base_color)
        self._stripe_path = os.path.join(
            tempfile.gettempdir(), f"felfel_stripe_{id(self)}.png"
        )
        self._stripe_pixmap.save(self._stripe_path, "PNG")

    def _build_style(self):
        if self._striped and self._stripe_pixmap:
            bg = f'url("{self._stripe_path}") repeat'
        else:
            bg = self._base_color

        return f"""
            QProgressBar {{
                border: none;
                border-radius: 8px;
                background: palette(midlight);
            }}
            QProgressBar::chunk {{
                border-radius: 8px;
                background: {bg};
            }}
        """

    def set_color(self, color: str):
        self._base_color = color
        self._build_pixmap()
        self.setStyleSheet(self._build_style())

    def set_striped(self, striped: bool, stripe_color: str = None):
        self._striped = striped
        if stripe_color:
            self._stripe_color = stripe_color
        self._build_pixmap()
        self.setStyleSheet(self._build_style())

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.value() >= self.maximum():
            return

        rect = self.rect()
        value_range = self.maximum() - self.minimum()
        if value_range <= 0:
            return

        fraction = (self.value() - self.minimum()) / value_range
        filled_width = int(rect.width() * fraction)
        if filled_width <= 0:
            return

        radius = 8
        cover_width = radius
        cover_rect = QRect(
            filled_width - cover_width,
            0,
            cover_width,
            rect.height(),
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(Qt.PenStyle.NoPen)

        if self._striped:
            painter.setClipRect(cover_rect)
            painter.drawTiledPixmap(rect, self._stripe_pixmap, QPoint(0, 0))
        else:
            painter.setBrush(QBrush(QColor(self._base_color)))
            painter.drawRect(cover_rect)

        painter.end()


# ═══════════════════════════════════════════════════════════════════
# Add / Quick / Single / YouTube dialogs
# ═══════════════════════════════════════════════════════════════════


class AddDownloadDialog(QDialog):
    """
    Unified dialog for adding downloads.

    Tabs:
        Basic   — URLs, file list, rule banner, queue, save path
        Options — connections, per-download speed limit, proxy

    The OK/Cancel buttons live outside the tabs so they are reachable
    from any tab. The file table is shown only when there is more than
    one URL (or once a fetch has started), keeping the single-URL flow
    minimal.
    """

    FETCH_DEBOUNCE_MS = 800

    def __init__(self, queues, default_queue=0, parent=None):
        super().__init__(None)
        self._main_window = parent

        self.setWindowTitle("Add Download")
        self.setMinimumWidth(560)
        self.setSizeGripEnabled(True)

        self.queues = queues
        self.default_queue = default_queue
        self._visible_queues = [q for q in self.queues if q.name != "__direct__"]
        self._custom_proxy = None
        self._path_user_edited = False

        self._url_to_row: dict = {}
        self._url_to_size: dict = {}
        self._url_to_status: dict = {}

        self._fetch_timer = QTimer(self)
        self._fetch_timer.setSingleShot(True)
        self._fetch_timer.timeout.connect(self._start_fetching_sizes)

        self._fetcher: "SizeFetcherWorker" = None

        self._build_ui()
        self._setup_tab_order()

    # ─────────────────────────────────────────────────────────────
    # Small helpers
    # ─────────────────────────────────────────────────────────────

    def _make_separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("background-color: palette(mid); max-height: 1px;")
        return line

    # ─────────────────────────────────────────────────────────────
    # UI construction
    # ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 12)

        # ═══════════════════════════════════════════════════════════
        # Tabs
        # ═══════════════════════════════════════════════════════════
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                border-top: 1px solid palette(mid);
                top: -1px;
            }
            QTabBar {
                background: transparent;
            }
            QTabBar::tab {
                background: transparent;
                padding: 6px 14px;
                margin-right: 2px;
                border: none;
                border-bottom: 2px solid transparent;
            }
            QTabBar::tab:selected {
                border-bottom: 2px solid #89b4fa;
            }
        """)
        main_layout.addWidget(self.tabs, 1)

        # ─────────────────────────────────────────────────────────
        # TAB 1: Basic
        # ─────────────────────────────────────────────────────────
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)
        basic_layout.setSpacing(8)
        basic_layout.setContentsMargins(4, 10, 4, 4)

        # URLs label + editor
        url_label = QLabel("URLs")
        url_label.setStyleSheet("font-weight: 600; font-size: 12px;")
        basic_layout.addWidget(url_label)

        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText(
            "Enter URLs (one per line)...\n\nTip: Paste multiple URLs at once."
        )
        self.url_edit.setMinimumHeight(70)
        self.url_edit.setMaximumHeight(110)
        self.url_edit.textChanged.connect(self._on_urls_changed)
        basic_layout.addWidget(self.url_edit)

        # Import + Fetch buttons
        url_btn_row = QHBoxLayout()
        url_btn_row.setSpacing(6)

        self.import_btn = QPushButton(get_icon("document-open"), " Import")
        self.import_btn.setToolTip("Import URLs from a text file")
        self.import_btn.setFixedHeight(28)
        self.import_btn.clicked.connect(self._import_from_txt)
        url_btn_row.addWidget(self.import_btn)

        self.fetch_btn = QPushButton(get_icon("view-refresh"), " Fetch sizes")
        self.fetch_btn.setToolTip("Fetch file sizes for all URLs")
        self.fetch_btn.setFixedHeight(28)
        self.fetch_btn.clicked.connect(self._start_fetching_sizes)
        url_btn_row.addWidget(self.fetch_btn)
        
        # Fetch status chip
        self.fetch_chip = QLabel("")
        self.fetch_chip.setStyleSheet("""
            QLabel {
                background-color: #89b4fa;
                color: #1e1e2e;
                border-radius: 9px;
                padding: 1px 10px;
                font-size: 10px;
                font-weight: 600;
            }
        """)
        self.fetch_chip.setFixedHeight(18)
        self.fetch_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fetch_chip.setVisible(False)
        
        
        url_btn_row.addWidget(self.fetch_chip)

        url_btn_row.addStretch()
        basic_layout.addLayout(url_btn_row)


        # Rule banner (only shown when a rule matches a URL)
        self.rule_banner = QFrame()
        self.rule_banner.setObjectName("rule_banner")
        self.rule_banner.setStyleSheet("""
            QFrame#rule_banner {
                background-color: rgba(137, 180, 250, 0.15);
                border: 1px solid #89b4fa;
                border-radius: 4px;
                padding: 4px;
            }
        """)
        self.rule_banner.setVisible(False)

        banner_layout = QHBoxLayout(self.rule_banner)
        banner_layout.setContentsMargins(8, 4, 8, 4)
        banner_layout.setSpacing(8)

        self.rule_banner_icon = QLabel("🎯")
        self.rule_banner_icon.setStyleSheet("font-size: 14px;")
        banner_layout.addWidget(self.rule_banner_icon)

        self.rule_banner_label = QLabel("")
        self.rule_banner_label.setWordWrap(True)
        self.rule_banner_label.setStyleSheet(
            "color: #89b4fa; font-size: 11px; font-weight: 500;"
        )
        banner_layout.addWidget(self.rule_banner_label, 1)

        basic_layout.addWidget(self.rule_banner)

        # Files table (only shown when more than one URL)
        self.files_container = QWidget()
        files_layout = QVBoxLayout(self.files_container)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.setSpacing(4)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["", "Filename", "Size", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setMinimumHeight(120)
        self.table.setMaximumHeight(180)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 36)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)

        files_layout.addWidget(self.table)

        select_row = QHBoxLayout()
        select_row.setSpacing(6)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setFixedHeight(28)
        self.select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_row.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.setFixedHeight(28)
        self.deselect_all_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(self.deselect_all_btn)

        select_row.addStretch()
        files_layout.addLayout(select_row)

        self.files_container.setVisible(False)
        basic_layout.addWidget(self.files_container)

        # Total label
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        basic_layout.addWidget(self.total_label)

        # Queue row
        queue_row = QHBoxLayout()
        queue_row.setSpacing(8)

        queue_label = QLabel("Queue:")
        queue_label.setFixedWidth(60)
        queue_row.addWidget(queue_label)

        self.queue_cb = QComboBox()
        self.queue_cb.addItem("📥 Direct Downloads", "__direct__")
        for q in self._visible_queues:
            self.queue_cb.addItem(q.name, q.name)
        if 0 <= self.default_queue < self.queue_cb.count():
            self.queue_cb.setCurrentIndex(self.default_queue)
        self.queue_cb.currentIndexChanged.connect(self._on_queue_selection_changed)
        queue_row.addWidget(self.queue_cb, 1)

        basic_layout.addLayout(queue_row)

        self.queue_hint = QLabel("Downloads start immediately — no queue, no waiting.")
        self.queue_hint.setWordWrap(True)
        self.queue_hint.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding-left: 68px;"
        )
        basic_layout.addWidget(self.queue_hint)
        
        self.queue_help_label = QLabel("")
        self.queue_help_label.setWordWrap(True)
        self.queue_help_label.setStyleSheet(
            "color: #f39c12; font-size: 10px; padding-left: 68px;"
        )
        self.queue_help_label.setVisible(False)
        basic_layout.addWidget(self.queue_help_label)

        # Save-to row
        save_row = QHBoxLayout()
        save_row.setSpacing(6)

        save_label = QLabel("Save to:")
        save_label.setFixedWidth(60)
        save_row.addWidget(save_label)

        default_path = self._default_path_for_index(self.default_queue)
        self.path_edit = QLineEdit(default_path)
        self.path_edit.textEdited.connect(self._on_path_manually_edited)
        save_row.addWidget(self.path_edit, 1)

        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        save_row.addWidget(self.browse_btn)

        basic_layout.addLayout(save_row)
        basic_layout.addStretch()

        self.tabs.addTab(basic_tab, "Basic")

        # ─────────────────────────────────────────────────────────
        # TAB 2: Options
        # ─────────────────────────────────────────────────────────
        options_tab = QWidget()
        options_layout = QVBoxLayout(options_tab)
        options_layout.setSpacing(10)
        options_layout.setContentsMargins(4, 10, 4, 4)

        # Connections
        conn_row = QHBoxLayout()
        conn_row.setSpacing(8)

        conn_label = QLabel("Connections:")
        conn_label.setFixedWidth(100)
        conn_row.addWidget(conn_label)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        self.conn_spin.setFixedWidth(80)
        conn_row.addWidget(self.conn_spin)
        conn_row.addStretch()

        options_layout.addLayout(conn_row)

        options_layout.addWidget(self._make_separator())

        # Speed limit
        speed_title = QLabel("Speed Limit")
        f = speed_title.font()
        f.setBold(True)
        speed_title.setFont(f)
        options_layout.addWidget(speed_title)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(8)

        self.per_download_speed_cb = QCheckBox("Limit speed for this download")
        self.per_download_speed_cb.setChecked(False)
        speed_row.addWidget(self.per_download_speed_cb)

        self.per_download_speed_spin = QSpinBox()
        self.per_download_speed_spin.setRange(0, 999999)
        self.per_download_speed_spin.setSuffix(" KB/s")
        self.per_download_speed_spin.setValue(1024)
        self.per_download_speed_spin.setEnabled(False)
        self.per_download_speed_spin.setFixedWidth(130)
        self.per_download_speed_cb.toggled.connect(
            self.per_download_speed_spin.setEnabled
        )
        speed_row.addWidget(self.per_download_speed_spin)
        speed_row.addStretch()

        options_layout.addLayout(speed_row)

        speed_hint = QLabel(
            "When set, this overrides the queue and global speed limits "
            "for this download only."
        )
        speed_hint.setStyleSheet("color: #95a5a6; font-size: 10px;")
        speed_hint.setWordWrap(True)
        options_layout.addWidget(speed_hint)

        options_layout.addWidget(self._make_separator())

        # Proxy
        proxy_title = QLabel("Proxy")
        f = proxy_title.font()
        f.setBold(True)
        proxy_title.setFont(f)
        options_layout.addWidget(proxy_title)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            ["Use Global/Queue Proxy", "Custom Proxy", "No Proxy"]
        )
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        options_layout.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        options_layout.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        options_layout.addWidget(self.proxy_status_label)

        options_layout.addStretch()

        self.tabs.addTab(options_tab, "Options")

        # ═══════════════════════════════════════════════════════════
        # Buttons (outside the tabs, always visible)
        # ═══════════════════════════════════════════════════════════
        main_layout.addSpacing(4)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        ok_btn = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
        cancel_btn = self.btn_box.button(QDialogButtonBox.StandardButton.Cancel)

        ok_btn.setText("Download")
        ok_btn.setIcon(get_icon("download"))
        ok_btn.setMinimumWidth(140)
        ok_btn.setFixedHeight(34)

        cancel_btn.setMinimumWidth(100)
        cancel_btn.setFixedHeight(34)

        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        ok_btn.setEnabled(False)

        main_layout.addWidget(self.btn_box)

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.import_btn)
        self.setTabOrder(self.import_btn, self.fetch_btn)
        self.setTabOrder(self.fetch_btn, self.table)
        self.setTabOrder(self.table, self.queue_cb)
        self.setTabOrder(self.queue_cb, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.conn_spin)
        self.setTabOrder(self.conn_spin, self.per_download_speed_cb)
        self.setTabOrder(self.per_download_speed_cb, self.per_download_speed_spin)
        self.setTabOrder(self.per_download_speed_spin, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.btn_box)

    # ─────────────────────────────────────────────────────────────
    # URL handling
    # ─────────────────────────────────────────────────────────────

    def _on_urls_changed(self):
        urls = self._get_urls()
        show_table = len(urls) > 1

        self.files_container.setVisible(show_table)

        # Direct Downloads is only valid for a single URL. For a batch,
        # grey it out so the user sees it exists but can't select it,
        # and move the selection to the first real queue if needed.
        model = self.queue_cb.model()
        direct_item = model.item(0) if hasattr(model, "item") else None
        if direct_item is not None:
            allow_direct = not show_table
            direct_item.setEnabled(allow_direct)

            if allow_direct:
                direct_item.setToolTip("")
            else:
                direct_item.setToolTip(
                    "Direct Downloads is only available for a single URL.\n"
                    "For batch downloads, choose a queue."
                )

            if not allow_direct and self.queue_cb.currentData() == "__direct__":
                for i in range(1, self.queue_cb.count()):
                    other = model.item(i) if hasattr(model, "item") else None
                    if other is None or other.isEnabled():
                        self.queue_cb.setCurrentIndex(i)
                        break

        # Show the "why is Direct greyed out" hint for multi-URL batches
        if show_table:
            self.queue_help_label.setText(
                "💡 Multiple URLs — Direct Downloads is disabled. "
                "Pick a queue to batch these downloads."
            )
            self.queue_help_label.setVisible(True)
        else:
            self.queue_help_label.setVisible(False)

        self._fetch_timer.start(self.FETCH_DEBOUNCE_MS)
    def _get_urls(self):
        raw = self.url_edit.toPlainText()
        urls = []
        for line in raw.split("\n"):
            line = line.strip()
            if line and line not in urls:
                urls.append(line)
        return urls

    def _extract_filename(self, url: str) -> str:
        raw = url.split("/")[-1]
        clean = raw.split("?")[0] if "?" in raw else raw
        return clean if clean else "Unknown"

    # ─────────────────────────────────────────────────────────────
    # Fetch sizes
    # ─────────────────────────────────────────────────────────────

    def _start_fetching_sizes(self):
        urls = self._get_urls()
        if not urls:
            self._clear_table()
            self._hide_fetch_chip()
            return

        self._cancel_fetcher()

        self._url_to_row = {}
        self._url_to_size = {}
        self._url_to_status = {}

        self._populate_table(urls)
        self._update_rule_banner(urls)

        show_table = len(urls) > 1
        self.files_container.setVisible(show_table)

        self._show_fetch_chip(f"🔄  0/{len(urls)}", "#89b4fa")

        proxy = self._get_proxy_dict_for_fetch()

        self._fetcher = SizeFetcherWorker(urls, proxy=proxy)
        self._fetcher.size_fetched.connect(self._on_size_fetched)
        self._fetcher.fetch_failed.connect(self._on_fetch_failed)
        self._fetcher.progress.connect(self._on_fetch_progress)
        self._fetcher.all_done.connect(self._on_fetch_done)
        self._fetcher.start()
        
    def _show_fetch_chip(self, text: str, color: str) -> None:
        """Show the fetch status chip with the given text and background."""
        self.fetch_chip.setText(text)
        self.fetch_chip.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: #1e1e2e;
                border-radius: 9px;
                padding: 1px 10px;
                font-size: 10px;
                font-weight: 600;
            }}
        """)
        self.fetch_chip.setVisible(True)

    def _hide_fetch_chip(self) -> None:
        self.fetch_chip.setVisible(False)
        
    def _on_fetch_progress(self, done, total):
        self._show_fetch_chip(f"Fetching {done}/{total}", "#89b4fa")

    def _update_rule_banner(self, urls):
        if not self._main_window or not hasattr(self._main_window, "store"):
            self.rule_banner.setVisible(False)
            return

        rule_engine = self._main_window.store.rule_engine

        matches = []
        for url in urls:
            rule = rule_engine.find_match(url)
            if rule:
                matches.append((url, rule))

        if not matches:
            self.rule_banner.setVisible(False)
            return

        if len(matches) == 1:
            url, rule = matches[0]
            filename = self._extract_filename(url)
            actions = []
            if rule.queue:
                actions.append(f"Queue: {rule.queue}")
            if rule.folder:
                actions.append(f"Folder: {rule.folder}")
            if rule.connections:
                actions.append(f"Connections: {rule.connections}")
            if rule.speed_limit:
                actions.append(f"Speed: {rule.speed_limit} KB/s")

            actions_str = "  •  ".join(actions) if actions else "(no actions)"
            self.rule_banner_label.setText(
                f"Rule '<b>{rule.name}</b>' will be applied to "
                f"'{filename}'<br>"
                f"<span style='font-size: 10px; color: #a6adc8;'>{actions_str}</span>"
            )
        else:
            rule_names = list({rule.name for _, rule in matches})
            self.rule_banner_label.setText(
                f"<b>{len(matches)}</b> URL(s) will match "
                f"<b>{len(rule_names)}</b> rule(s): "
                f"{', '.join(rule_names)}"
            )

        self.rule_banner.setVisible(True)

    def _cancel_fetcher(self):
        if self._fetcher is None:
            return

        fetcher = self._fetcher
        self._fetcher = None

        try:
            fetcher.cancel()
            try:
                fetcher.size_fetched.disconnect()
                fetcher.fetch_failed.disconnect()
                fetcher.progress.disconnect()
                fetcher.all_done.disconnect()
            except (TypeError, RuntimeError):
                pass

            if not fetcher.wait(2000):
                fetcher.terminate()
                fetcher.wait(500)

            fetcher.deleteLater()
        except RuntimeError:
            pass

    def _get_proxy_dict_for_fetch(self):
        proxy_mode = (
            self.proxy_combo.currentIndex() if hasattr(self, "proxy_combo") else 0
        )
        try:
            if proxy_mode == 0 and self._main_window is not None:
                if hasattr(self._main_window, "proxy_manager"):
                    p = self._main_window.proxy_manager.get_proxy_for_queue(None)
                    if p and p.is_valid() and p.enabled:
                        url = p._build_proxy_url()
                        return {"http": url, "https": url}
            elif proxy_mode == 1 and self._custom_proxy is not None:
                if self._custom_proxy.is_valid():
                    url = self._custom_proxy._build_proxy_url()
                    return {"http": url, "https": url}
        except Exception as e:
            print(f"⚠️ [AddDownloadDialog] Could not build proxy dict: {e}")
        return None

    # ─────────────────────────────────────────────────────────────
    # Table population & updates
    # ─────────────────────────────────────────────────────────────

    def _clear_table(self):
        self.table.setRowCount(0)
        self._url_to_row = {}
        self._url_to_size = {}
        self._url_to_status = {}
        self.btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self._hide_fetch_chip()
        self._update_total()

    def _populate_table(self, urls):
        self.table.setRowCount(0)
        self.btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        for url in urls:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._url_to_row[url] = row
            self._url_to_size[url] = None
            self._url_to_status[url] = "fetching"

            cb = QCheckBox()
            cb.setChecked(True)
            cb.stateChanged.connect(self._update_total)
            cb.setStyleSheet("""
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                }
            """)
            cb_widget = _ClickableCheckboxWidget(cb)
            self.table.setCellWidget(row, 0, cb_widget)

            name = self._extract_filename(url)
            name_item = QTableWidgetItem(name)
            name_item.setToolTip(url)
            self.table.setItem(row, 1, name_item)

            size_item = QTableWidgetItem("⏳ Fetching...")
            self.table.setItem(row, 2, size_item)

            status_item = QTableWidgetItem("")
            self.table.setItem(row, 3, status_item)

        self._update_total()

    def _on_size_fetched(self, url, size):
        row = self._url_to_row.get(url)
        if row is None:
            return

        if self._url_to_status.get(url) == "done":
            return

        try:
            size = int(size)
        except (ValueError, TypeError):
            return

        if size <= 0:
            return

        self._url_to_size[url] = size
        self._url_to_status[url] = "done"
        self.table.item(row, 2).setText(format_size(size))

        status_item = self.table.item(row, 3)
        status_item.setText("Success")
        status_item.setForeground(QColor("#27ae60"))

        self._update_total()
    
    def _on_fetch_failed(self, url, error):
        row = self._url_to_row.get(url)
        if row is None:
            return

        if self._url_to_status.get(url) == "failed":
            return

        self._url_to_size[url] = None
        self._url_to_status[url] = "failed"
        self.table.item(row, 2).setText("Unknown")

        status_item = self.table.item(row, 3)
        status_item.setText("Failed")
        status_item.setForeground(QColor("#e74c3c"))

        self._update_total()

    def _on_fetch_done(self):
        fetcher = self._fetcher
        self._fetcher = None
        if fetcher is not None:
            try:
                fetcher.deleteLater()
            except RuntimeError:
                pass

        total = self.table.rowCount()
        if total > 0:
            self._show_fetch_chip(f"Done", "#a6e3a1")
        else:
            self._hide_fetch_chip()

        self._update_total()

        # Hide the chip shortly after so it doesn't stay there forever
        QTimer.singleShot(1800, self._hide_fetch_chip)

    def _set_all_checked(self, checked: bool):
        for row in range(self.table.rowCount()):
            w = self.table.cellWidget(row, 0)
            if isinstance(w, _ClickableCheckboxWidget):
                w.set_checked(checked)
        self._update_total()

    def _get_selected_urls(self):
        urls = self._get_urls()

        # For a single URL, the table is hidden; the URL itself is the
        # selection.
        if len(urls) <= 1:
            return urls

        selected = []
        for url, row in self._url_to_row.items():
            w = self.table.cellWidget(row, 0)
            if isinstance(w, _ClickableCheckboxWidget) and w.is_checked():
                selected.append(url)
        return selected

    def _update_total(self):
        selected_urls = self._get_selected_urls()
        ok_btn = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)

        if ok_btn is not None:
            ok_btn.setEnabled(bool(selected_urls))

        if not selected_urls:
            self.total_label.setText("No files selected")
            return

        total_bytes = 0
        unknown = 0
        for url in selected_urls:
            size = self._url_to_size.get(url)
            if size and size > 0:
                total_bytes += size
            else:
                unknown += 1

        parts = [f"{len(selected_urls)} file(s) selected"]
        if total_bytes > 0:
            parts.append(f"Total: {format_size(total_bytes)}")
        if unknown > 0:
            parts.append(f"({unknown} unknown)")
        self.total_label.setText("  •  ".join(parts))

    # ─────────────────────────────────────────────────────────────
    # Browse / import
    # ─────────────────────────────────────────────────────────────

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)
            self._path_user_edited = True

    def _default_path_for_index(self, index):
        if 0 <= index < len(self._visible_queues):
            save_path = self._visible_queues[index].save_path
            if save_path:
                return save_path
        return os.path.expanduser("~/Downloads")

    def _on_path_manually_edited(self, _text):
        self._path_user_edited = True

    def _on_queue_selection_changed(self, index):
        queue_name = self.queue_cb.currentData()

        if hasattr(self, "queue_hint"):
            if queue_name == "__direct__":
                self.queue_hint.setText(
                    "Downloads start immediately — no queue, no waiting."
                )
                self.queue_hint.setStyleSheet(
                    "color: #95a5a6; font-size: 10px; padding-left: 68px;"
                )
            else:
                q = next(
                    (q for q in self._visible_queues if q.name == queue_name),
                    None,
                )
                if q and q.paused:
                    self.queue_hint.setText(
                        f"⚠️ Queue '{q.name}' is paused — downloads will wait "
                        f"until the queue is started."
                    )
                    self.queue_hint.setStyleSheet(
                        "color: #f39c12; font-size: 10px; padding-left: 68px;"
                    )
                elif q:
                    self.queue_hint.setText(
                        f"Queue '{q.name}' is active — downloads will start "
                        f"immediately."
                    )
                    self.queue_hint.setStyleSheet(
                        "color: #95a5a6; font-size: 10px; padding-left: 68px;"
                    )

        if self._path_user_edited:
            return

        if queue_name == "__direct__":
            self.path_edit.setText(os.path.expanduser("~/Downloads"))
        else:
            for q in self._visible_queues:
                if q.name == queue_name:
                    self.path_edit.setText(
                        q.save_path or os.path.expanduser("~/Downloads")
                    )
                    break

    def _import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Links File", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    current = self.url_edit.toPlainText().strip()
                    combined = (
                        current + "\n" + "\n".join(lines)
                        if current
                        else "\n".join(lines)
                    )
                    self.url_edit.setPlainText(combined)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse file:\n{str(e)}")

    # ─────────────────────────────────────────────────────────────
    # Proxy helpers
    # ─────────────────────────────────────────────────────────────

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import SimpleProxyDialog

        urls = self._get_urls()
        display_name = self._extract_filename(urls[0]) if urls else "Download"
        dlg = SimpleProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._custom_proxy = new_config
            self.proxy_clear_btn.setEnabled(True)
            self._update_proxy_status()
            self._start_fetching_sizes()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.proxy_status_label.setText("Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")

    # ─────────────────────────────────────────────────────────────
    # Data extraction & cleanup
    # ─────────────────────────────────────────────────────────────

    def get_data(self):
        urls = self._get_selected_urls()
        proxy_mode = self.proxy_combo.currentIndex()

        per_download_speed = 0
        if self.per_download_speed_cb.isChecked():
            per_download_speed = self.per_download_speed_spin.value()

        data = {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
            "per_download_speed": per_download_speed,
        }

        data["queue_name"] = self.queue_cb.currentData()
        data["queue"] = -1

        return data

    def closeEvent(self, event):
        self._cancel_fetcher()
        event.accept()


class YouTubeDownloadDialog(QDialog):
    youtube_download_requested = pyqtSignal(dict)

    def __init__(self, parent=None, queues=None, default_queue=0):
        super().__init__(None)
        self._main_window = parent
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(600)
        self.setMinimumHeight(200)
        self.setSizeGripEnabled(True)

        self.queues = queues or []
        self.default_queue = default_queue
        self.video_info = None
        self._custom_proxy = None
        self._format_map = {}
        self.worker = None
        self._path_user_edited = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 16)

        video_acc = AccordionGroup("Video")
        video_acc.set_expanded(True)

        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_row.addWidget(self.url_edit)

        self.fetch_btn = QPushButton(get_icon("view-refresh"), " Get Info")
        self.fetch_btn.setFixedHeight(32)
        self.fetch_btn.clicked.connect(self._fetch_info)
        url_row.addWidget(self.fetch_btn)
        video_acc.addLayout(url_row)

        info_group = QGroupBox("Video Info")
        self.info_layout = QFormLayout(info_group)
        self.info_layout.setSpacing(6)

        self.info_placeholder = QLabel("Enter a YouTube URL and click 'Get Info'")
        self.info_placeholder.setStyleSheet("color: #95a5a6; font-size: 11px;")
        self.info_layout.addRow(self.info_placeholder)

        video_acc.addWidget(info_group)

        main_layout.addWidget(video_acc)

        opts_acc = AccordionGroup("Options")
        opts_acc.set_expanded(True)

        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        opts_acc.addWidget(self.format_combo)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        self.path_edit.textEdited.connect(self._on_path_manually_edited)
        path_row.addWidget(self.path_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.browse_btn)
        opts_acc.addLayout(path_row)

        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(6)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("Optional: cookies.txt path")
        cookie_row.addWidget(self.cookie_edit)
        self.cookie_browse = QPushButton()
        self.cookie_browse.setIcon(get_icon("folder-open"))
        self.cookie_browse.setFixedSize(28, 28)
        self.cookie_browse.clicked.connect(self._browse_cookie)
        cookie_row.addWidget(self.cookie_browse)
        opts_acc.addLayout(cookie_row)

        self.queue_combo = QComboBox()
        self.queue_combo.addItem("Direct Downloads", "__direct__")
        for i, q in enumerate(self.queues):
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, q.name)
        if self.default_queue < self.queue_combo.count():
            self.queue_combo.setCurrentIndex(self.default_queue)
        self.queue_combo.currentIndexChanged.connect(self._on_queue_selection_changed)
        opts_acc.addWidget(self.queue_combo)

        self._on_queue_selection_changed(self.queue_combo.currentIndex())
        self._path_user_edited = False

        main_layout.addWidget(opts_acc)

        proxy_acc = AccordionGroup("Proxy Settings")
        proxy_acc.set_expanded(False)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(["Use Global Proxy", "Custom Proxy", "No Proxy"])
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_acc.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        proxy_acc.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        proxy_acc.addWidget(self.proxy_status_label)

        main_layout.addWidget(proxy_acc)

        self.btn_box = QDialogButtonBox()
        self.download_btn = self.btn_box.addButton(
            "Add to Queue", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.download_btn.setIcon(get_icon("download"))
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_add_to_queue)

        self.cancel_btn = self.btn_box.addButton(
            "Cancel", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.cancel_btn.setIcon(get_icon("dialog-cancel"))
        self.cancel_btn.clicked.connect(self.reject)

        main_layout.addWidget(self.btn_box)

        self._setup_tab_order()

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.fetch_btn)
        self.setTabOrder(self.fetch_btn, self.format_combo)
        self.setTabOrder(self.format_combo, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.cookie_edit)
        self.setTabOrder(self.cookie_edit, self.cookie_browse)
        self.setTabOrder(self.cookie_browse, self.queue_combo)
        self.setTabOrder(self.queue_combo, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.download_btn)
        self.setTabOrder(self.download_btn, self.cancel_btn)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)
            self._path_user_edited = True

    def _on_path_manually_edited(self, _text):
        self._path_user_edited = True

    def _on_queue_selection_changed(self, _index):
        if self._path_user_edited:
            return
        queue_name = self.queue_combo.currentData()
        if queue_name == "__direct__":
            self.path_edit.setText(os.path.expanduser("~/Downloads"))
            return
        for q in self.queues:
            if q.name == queue_name:
                self.path_edit.setText(q.save_path or os.path.expanduser("~/Downloads"))
                return

    def _browse_cookie(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cookies File", "", "Cookies Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookie_edit.setText(file_path)

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import SimpleProxyDialog

        url = self.url_edit.text().strip()
        display_name = os.path.basename(url) if url else "YouTube Download"
        dlg = SimpleProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._custom_proxy = new_config
            self.proxy_clear_btn.setEnabled(True)
            self._update_proxy_status()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")

    def _get_proxy_url(self):
        proxy_mode = self.proxy_combo.currentIndex()
        if proxy_mode == 0:
            if hasattr(self._main_window, "proxy_manager"):
                proxy = self._main_window.proxy_manager.get_proxy_for_queue(None)
                if proxy and proxy.is_valid():
                    return proxy._build_proxy_url()
        elif proxy_mode == 1:
            if self._custom_proxy and self._custom_proxy.is_valid():
                return self._custom_proxy._build_proxy_url()
        return None

    def clear_info_layout(self):
        while self.info_layout.rowCount() > 0:
            self.info_layout.removeRow(self.info_layout.rowCount() - 1)

    def _fetch_info(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL")
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching...")

        self.clear_info_layout()
        self.info_placeholder = QLabel("Getting video info...")
        self.info_placeholder.setStyleSheet("color: #3daee9; font-size: 11px;")
        self.info_layout.addRow(self.info_placeholder)

        try:
            from core.youtube_worker import YouTubeWorker

            cookie_file = self.cookie_edit.text().strip() or None
            proxy_url = self._get_proxy_url()

            self.worker = YouTubeWorker(url, "", "mp4", cookie_file, proxy_url)
            self.worker.is_fetching_info = True
            self.worker.info_fetched.connect(self._on_info_fetched)
            self.worker.finished.connect(self._on_info_fetch_finished)
            self.worker.start()

        except Exception as e:
            self.clear_info_layout()
            self.info_placeholder = QLabel(f"Error: {str(e)}")
            self.info_placeholder.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.info_layout.addRow(self.info_placeholder)
            self.fetch_btn.setEnabled(True)
            self.fetch_btn.setText("Get Info")

    def _on_info_fetched(self, info):
        self.video_info = info
        self.clear_info_layout()

        title = info.get("title", "Unknown")
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: 600;")
        self.info_layout.addRow("Title:", title_label)

        uploader = info.get("uploader", "Unknown")
        self.info_layout.addRow("Channel:", QLabel(uploader))

        duration = info.get("duration", 0)
        minutes = duration // 60
        seconds = duration % 60
        self.info_layout.addRow("Duration:", QLabel(f"{minutes}:{seconds:02d}"))

        formats = info.get("formats", [])
        self.format_combo.clear()
        self._format_map = {}

        video_formats = []
        audio_formats = []

        for f in formats:
            format_id = f.get("format_id")
            resolution = f.get("resolution")
            ext = f.get("ext")
            filesize = f.get("filesize")
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")

            if vcodec and vcodec != "none":
                label = f"Video ({ext.upper()})"
                if resolution and resolution != "audio only":
                    label += f" - {resolution}"
                if filesize:
                    label += f" ({format_size(filesize)})"
                video_formats.append((format_id, label, f))

            elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                bitrate = f.get("abr")
                label = f"Audio ({ext.upper()})"
                if bitrate:
                    label += f" - {bitrate}kbps"
                if filesize:
                    label += f" ({format_size(filesize)})"
                audio_formats.append((format_id, label, f))

        def sort_key(item):
            resolution = item[2].get("resolution", "")
            if "p" in resolution:
                return int(resolution.replace("p", ""))
            return 0

        video_formats.sort(key=sort_key, reverse=True)

        for format_id, label, f in video_formats:
            self.format_combo.addItem(label, format_id)
            self._format_map[format_id] = f

        if audio_formats:
            self.format_combo.addItem("--- Audio Only ---", None)
            for format_id, label, f in audio_formats:
                self.format_combo.addItem(label, format_id)
                self._format_map[format_id] = f

        if video_formats:
            self.format_combo.insertItem(0, "Best Quality", "best")

        self.format_combo.setCurrentIndex(0)

        if video_formats:
            quality_labels = [
                f[2].get("resolution", "Unknown") for f in video_formats[:5]
            ]
            self.info_layout.addRow("Qualities:", QLabel(", ".join(quality_labels)))

        filesize = info.get("filesize")
        if filesize:
            self.info_layout.addRow("Size:", QLabel(format_size(filesize)))

        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Info")

        QTimer.singleShot(100, self.adjustSize)

    def _on_info_fetch_finished(self, success, message):
        if not success:
            self.clear_info_layout()
            self.info_placeholder = QLabel(f"Error: {message}")
            self.info_placeholder.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.info_layout.addRow(self.info_placeholder)
            self.download_btn.setEnabled(False)

        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Info")

        QTimer.singleShot(100, self.adjustSize)

    def _on_add_to_queue(self):
        data = self.get_data()
        if not data["url"]:
            QMessageBox.warning(self, "Error", "Please enter a valid YouTube URL")
            return

        download_data = {
            "url": data["url"],
            "save_path": data["path"],
            "queue_id": data["queue_name"],
            "download_type": "youtube",
            "yt_options": {
                "quality": data.get("quality", "best"),
                "format": data.get("format", "video"),
                "cookies_path": data.get("cookie_file"),
                "title": data.get("video_info", {}).get("title", ""),
                "format_id": data.get("format_id"),
                "format_spec": data.get("format_spec", "bv+ba/b"),
                "format_info": data.get("format_info", {}),
            },
            "proxy": data.get("proxy_url"),
            "video_info": data.get("video_info"),
        }

        self.youtube_download_requested.emit(download_data)
        self.accept()

    def get_data(self):
        proxy_mode = self.proxy_combo.currentIndex()
        selected_format_id = self.format_combo.currentData()
        format_type = "video"
        quality = "best"

        if selected_format_id == "best":
            quality = "best"
            format_type = "video"
        elif selected_format_id == "bestaudio":
            quality = "best"
            format_type = "audio"
        else:
            format_info = self._format_map.get(selected_format_id, {})
            if format_info.get("vcodec") and format_info.get("vcodec") != "none":
                format_type = "video"
                quality = format_info.get("resolution", "best")
            elif format_info.get("acodec") and format_info.get("acodec") != "none":
                format_type = "audio"
                quality = format_info.get("abr", "best")
            else:
                format_type = "video"
                quality = "best"

        if selected_format_id == "best":
            format_spec = "bv+ba/b"
        elif selected_format_id == "bestaudio":
            format_spec = "ba/b"
        else:
            format_spec = selected_format_id

        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "format": format_type,
            "quality": quality,
            "format_id": selected_format_id,
            "format_spec": format_spec,
            "format_info": self._format_map.get(selected_format_id, {}),
            "cookie_file": self.cookie_edit.text().strip() or None,
            "video_info": self.video_info,
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
            "proxy_url": self._get_proxy_url(),
            "queue_name": self.queue_combo.currentData(),
        }


# ═══════════════════════════════════════════════════════════════════
# Settings dialogs
# ═══════════════════════════════════════════════════════════════════


class QueueSettingsDialog(QDialog):
    def __init__(self, queue: Queue, parent=None):
        super().__init__(None)
        self._main_window = parent
        self.setWindowTitle(f"Queue Settings — {queue.name}")
        self.setMinimumWidth(540)
        self.setMinimumHeight(300)
        self.setSizeGripEnabled(True)

        self.queue = queue
        self._queue_proxy_config = None
        self.disable_ssl_verify = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        tabs = QTabWidget()

        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)
        general_layout.setSpacing(10)
        general_layout.setContentsMargins(12, 12, 12, 12)

        self.name_edit = QLineEdit(queue.name)
        general_layout.addRow("Queue Name:", self.name_edit)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_edit = QLineEdit(queue.save_path)
        path_row.addWidget(self.path_edit)
        browse = QPushButton()
        browse.setIcon(get_icon("folder-open"))
        browse.setFixedSize(28, 28)
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        general_layout.addRow("Save Directory:", path_row)

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 20)
        self.conc_spin.setValue(queue.max_concurrent)
        general_layout.addRow("Max Concurrent:", self.conc_spin)

        tabs.addTab(general_tab, get_icon("configure"), "General")

        sched_tab = QWidget()
        sched_layout = QVBoxLayout(sched_tab)
        sched_layout.setSpacing(10)
        sched_layout.setContentsMargins(12, 12, 12, 12)

        self.sched_cb = QCheckBox("Enable Schedule")
        self.sched_cb.setChecked(queue.schedule_enabled)
        sched_layout.addWidget(self.sched_cb)

        time_row = QHBoxLayout()
        time_row.setSpacing(6)

        self.start_time = QTimeEdit(
            QTime(queue.schedule_start.hour, queue.schedule_start.minute)
        )
        self.end_time = QTimeEdit(
            QTime(queue.schedule_end.hour, queue.schedule_end.minute)
        )
        self.start_time.setDisplayFormat("HH:mm")
        self.end_time.setDisplayFormat("HH:mm")

        time_row.addWidget(QLabel("From:"))
        time_row.addWidget(self.start_time)
        time_row.addWidget(QLabel("To:"))
        time_row.addWidget(self.end_time)
        time_row.addStretch()
        sched_layout.addLayout(time_row)

        days_row = QHBoxLayout()
        days_row.setSpacing(4)
        self.day_checks = []
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            cb = QCheckBox(d)
            cb.setChecked(i in queue.days)
            self.day_checks.append(cb)
            days_row.addWidget(cb)
        days_row.addStretch()
        sched_layout.addLayout(days_row)

        sched_layout.addStretch()
        tabs.addTab(sched_tab, get_icon("alarm-clock"), "Schedule")

        speed_tab = QWidget()
        speed_layout = QVBoxLayout(speed_tab)
        speed_layout.setSpacing(10)
        speed_layout.setContentsMargins(12, 12, 12, 12)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)

        self.queue_speed_enabled = QCheckBox("Enable Speed Limit")
        self.queue_speed_enabled.setChecked(getattr(queue, "speed_limit", 0) > 0)
        self.queue_speed_enabled.toggled.connect(self._toggle_queue_speed)

        self.queue_speed_spin = QSpinBox()
        self.queue_speed_spin.setRange(0, 999999)
        self.queue_speed_spin.setSuffix(" KB/s")
        self.queue_speed_spin.setValue(getattr(queue, "speed_limit", 0) or 1024)
        self.queue_speed_spin.setEnabled(self.queue_speed_enabled.isChecked())
        self.queue_speed_spin.setMinimumWidth(120)

        speed_row.addWidget(self.queue_speed_enabled)
        speed_row.addWidget(self.queue_speed_spin)
        speed_row.addStretch()

        speed_layout.addLayout(speed_row)

        speed_info = QLabel("0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        speed_layout.addWidget(speed_info)

        speed_layout.addStretch()
        tabs.addTab(speed_tab, get_icon("preferences-system-speed"), "Speed")

        proxy_tab = QWidget()
        proxy_layout = QVBoxLayout(proxy_tab)
        proxy_layout.setSpacing(10)
        proxy_layout.setContentsMargins(12, 12, 12, 12)

        self.queue_proxy_cb = QCheckBox("Use custom proxy for this queue")
        self.queue_proxy_cb.toggled.connect(self._toggle_queue_proxy)
        proxy_layout.addWidget(self.queue_proxy_cb)

        proxy_row = QHBoxLayout()
        proxy_row.setSpacing(6)

        self.queue_proxy_status = QLabel("Using global proxy")
        proxy_row.addWidget(self.queue_proxy_status)
        proxy_row.addStretch()

        self.queue_proxy_btn = QPushButton(get_icon("configure"), " Configure")
        self.queue_proxy_btn.setEnabled(False)
        self.queue_proxy_btn.clicked.connect(self._configure_queue_proxy)
        proxy_row.addWidget(self.queue_proxy_btn)

        proxy_layout.addLayout(proxy_row)
        proxy_layout.addStretch()
        tabs.addTab(proxy_tab, get_icon("network-vpn"), "Proxy")

        main_layout.addWidget(tabs)

        tabs.currentChanged.connect(lambda idx: QTimer.singleShot(50, self.adjustSize))

        self._load_queue_proxy()

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

        self._cached_data = None

    def _on_accept(self):
        self._cached_data = self.get_queue_data()
        self.accept()

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _toggle_queue_speed(self, checked):
        self.queue_speed_spin.setEnabled(checked)

    def _toggle_queue_proxy(self, checked):
        self.queue_proxy_btn.setEnabled(checked)
        if checked:
            self.queue_proxy_status.setText("Click 'Configure' to set proxy")
            self.queue_proxy_status.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:
            self.queue_proxy_status.setText("Using global proxy")
            self.queue_proxy_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
            self._queue_proxy_config = None

    def _load_queue_proxy(self):
        from core.proxy_manager import ProxyManager

        if hasattr(self._main_window, "store"):
            proxy_mgr = ProxyManager(self._main_window.store)
            queue_proxy = proxy_mgr.get_queue_proxy(self.name_edit.text())
            if queue_proxy and queue_proxy.host:
                self.queue_proxy_cb.setChecked(True)
                self.queue_proxy_status.setText(f"✓ {queue_proxy.get_display_string()}")
                self.queue_proxy_status.setStyleSheet(
                    "color: #27ae60; font-size: 11px;"
                )
                self.queue_proxy_btn.setEnabled(True)
                self._queue_proxy_config = queue_proxy

    def _configure_queue_proxy(self):
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyConfig

        current = getattr(self, "_queue_proxy_config", None) or ProxyConfig()
        dlg = ProxyDialog(current, self, f"Queue Proxy: {self.name_edit.text()}")
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._queue_proxy_config = new_config
            self.queue_proxy_status.setText(f"✓ {new_config.get_display_string()}")
            self.queue_proxy_status.setStyleSheet("color: #27ae60; font-size: 11px;")

    def get_queue_data(self):
        st, en = self.start_time.time(), self.end_time.time()
        data = {
            "name": self.name_edit.text().strip(),
            "save_path": self.path_edit.text().strip(),
            "max_concurrent": self.conc_spin.value(),
            "schedule_enabled": self.sched_cb.isChecked(),
            "schedule_start": dtime(st.hour(), st.minute()),
            "schedule_end": dtime(en.hour(), en.minute()),
            "days": [i for i, cb in enumerate(self.day_checks) if cb.isChecked()],
            "speed_limit": (
                self.queue_speed_spin.value()
                if self.queue_speed_enabled.isChecked()
                else 0
            ),
            "proxy_config": None,
        }
        if hasattr(self, "_queue_proxy_config") and self.queue_proxy_cb.isChecked():
            data["proxy_config"] = self._queue_proxy_config
        return data


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(None)
        self._main_window = parent
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)
        self.setSizeGripEnabled(True)

        self.settings = settings

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        tabs = QTabWidget()

        # ── General ──
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setSpacing(10)
        general_layout.setContentsMargins(12, 12, 12, 12)

        rpc_group = QGroupBox("aria2 RPC")
        rpc_layout = QFormLayout(rpc_group)
        rpc_layout.setSpacing(6)

        self.host = QLineEdit(settings.get("aria2_host", "http://localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.get("aria2_port", 6800))
        self.secret = QLineEdit(settings.get("aria2_secret", ""))
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)

        rpc_layout.addRow("Host:", self.host)
        rpc_layout.addRow("Port:", self.port)
        rpc_layout.addRow("Secret:", self.secret)
        general_layout.addWidget(rpc_group)

        dl_group = QGroupBox("Download")
        dl_layout = QFormLayout(dl_group)
        dl_layout.setSpacing(6)

        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 50)
        self.max_concurrent.setValue(settings.get("max_concurrent", 5))

        self.max_retry_attempts = QSpinBox()
        self.max_retry_attempts.setRange(1, 20)
        self.max_retry_attempts.setValue(settings.get("max_retry_attempts", 5))
        self.max_retry_attempts.setToolTip(
            "Maximum number of automatic retry attempts for failed downloads"
        )

        self.max_tries = QSpinBox()
        self.max_tries.setRange(0, 100)
        self.max_tries.setSpecialValueText("Unlimited")
        self.max_tries.setValue(settings.get("max_tries", 0))

        self.conns = QSpinBox()
        self.conns.setRange(1, 16)
        self.conns.setValue(settings.get("connections", 8))

        self.retry_delay = QDoubleSpinBox()
        self.retry_delay.setRange(1.0, 60.0)
        self.retry_delay.setSingleStep(1.0)
        self.retry_delay.setValue(settings.get("retry_delay", 5.0))
        self.retry_delay.setSuffix(" seconds")
        self.retry_delay.setToolTip(
            "Delay between retry attempts (for transient errors only)"
        )

        self.retry_reset_after = QSpinBox()
        self.retry_reset_after.setRange(0, 3600)
        self.retry_reset_after.setSingleStep(10)
        self.retry_reset_after.setSpecialValueText("Never")
        self.retry_reset_after.setSuffix(" seconds")
        self.retry_reset_after.setValue(settings.get("retry_reset_after", 60))
        self.retry_reset_after.setToolTip(
            "If a retried download keeps downloading successfully for this long,\n"
            "its failed-attempt counter is reset to 0.\n"
            "Set to 'Never' to keep the counter until you restart the download."
        )

        dl_layout.addRow("Max Concurrent:", self.max_concurrent)
        dl_layout.addRow("Max Retry Attempts:", self.max_retry_attempts)
        dl_layout.addRow("Max Tries (aria2):", self.max_tries)
        dl_layout.addRow("Default Connections:", self.conns)
        dl_layout.addRow("Retry Delay:", self.retry_delay)
        dl_layout.addRow("Reset Retries After:", self.retry_reset_after)
        general_layout.addWidget(dl_group)

        cleanup_group = QGroupBox("Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        self.auto_clear_completed = QCheckBox("Auto-clear completed downloads")
        self.auto_clear_completed.setChecked(
            settings.get("auto_clear_completed", False)
        )
        cleanup_layout.addWidget(self.auto_clear_completed)
        general_layout.addWidget(cleanup_group)

        rules_group = QGroupBox("Download Rules")
        rules_layout = QVBoxLayout(rules_group)

        rules_info = QLabel(
            "Automatically apply actions (queue, folder, speed) based on URL, "
            "extension, domain, or size."
        )
        rules_info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        rules_info.setWordWrap(True)
        rules_layout.addWidget(rules_info)

        rules_btn = QPushButton(get_icon("configure"), "Manage Rules...")
        rules_btn.clicked.connect(self._open_rules_dialog)
        rules_layout.addWidget(rules_btn)
        general_layout.addWidget(rules_group)

        ssl_group = QGroupBox("SSL/TLS Settings")
        ssl_layout = QVBoxLayout(ssl_group)

        self.disable_ssl_verify = QCheckBox("Disable SSL certificate verification")
        self.disable_ssl_verify.setChecked(settings.get("disable_ssl_verify", False))
        self.disable_ssl_verify.setToolTip(
            "Disable SSL certificate verification for aria2 (use for self-signed certificates)"
        )
        ssl_layout.addWidget(self.disable_ssl_verify)

        warning_label = QLabel(
            "⚠️ Disabling SSL verification is insecure and should only be used for testing or with trusted self-signed certificates."
        )
        warning_label.setStyleSheet("color: #f39c12; font-size: 10px;")
        warning_label.setWordWrap(True)
        ssl_layout.addWidget(warning_label)

        general_layout.addWidget(ssl_group)
        general_layout.addStretch()

        tabs.addTab(general_tab, get_icon("configure"), "General")

        # ── Appearance ──
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        appearance_layout.setSpacing(10)
        appearance_layout.setContentsMargins(12, 12, 12, 12)

        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setSpacing(6)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Dark", "Light"])
        current_theme = settings.get("theme", "auto").capitalize()
        index = self.theme_combo.findText(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        theme_layout.addRow("Theme:", self.theme_combo)
        appearance_layout.addWidget(theme_group)

        appearance_layout.addStretch()
        tabs.addTab(appearance_tab, get_icon("preferences-desktop-theme"), "Appearance")

        # ── Speed ──
        speed_tab = QWidget()
        speed_layout = QVBoxLayout(speed_tab)
        speed_layout.setSpacing(10)
        speed_layout.setContentsMargins(12, 12, 12, 12)

        speed_group = QGroupBox("Global Speed Limit")
        speed_group_layout = QVBoxLayout(speed_group)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)

        self.global_speed_enabled = QCheckBox("Enable Speed Limit")
        self.global_speed_enabled.setChecked(settings.get("speed_limit", 0) > 0)
        self.global_speed_enabled.toggled.connect(self._toggle_global_speed)

        self.global_speed_spin = QSpinBox()
        self.global_speed_spin.setRange(0, 999999)
        self.global_speed_spin.setSuffix(" KB/s")
        self.global_speed_spin.setValue(settings.get("speed_limit", 1024))
        self.global_speed_spin.setEnabled(self.global_speed_enabled.isChecked())
        self.global_speed_spin.setMinimumWidth(120)

        speed_row.addWidget(self.global_speed_enabled)
        speed_row.addWidget(self.global_speed_spin)
        speed_row.addStretch()

        speed_group_layout.addLayout(speed_row)

        speed_info = QLabel("0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        speed_group_layout.addWidget(speed_info)

        speed_layout.addWidget(speed_group)
        speed_layout.addStretch()
        tabs.addTab(speed_tab, get_icon("preferences-system-speed"), "Speed")

        # ── Proxy ──
        proxy_tab = QWidget()
        proxy_layout = QVBoxLayout(proxy_tab)
        proxy_layout.setSpacing(10)
        proxy_layout.setContentsMargins(12, 12, 12, 12)

        proxy_group = QGroupBox("Global Proxy")
        proxy_group_layout = QVBoxLayout(proxy_group)

        proxy_status_row = QHBoxLayout()
        proxy_status_row.setSpacing(6)

        self.proxy_status_label = QLabel("Disabled")
        proxy_status_row.addWidget(self.proxy_status_label)
        proxy_status_row.addStretch()

        self.proxy_edit_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_edit_btn.clicked.connect(self._configure_global_proxy)
        proxy_status_row.addWidget(self.proxy_edit_btn)

        proxy_group_layout.addLayout(proxy_status_row)

        self.proxy_info_label = QLabel("")
        self.proxy_info_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        proxy_group_layout.addWidget(self.proxy_info_label)

        proxy_layout.addWidget(proxy_group)
        proxy_layout.addStretch()
        tabs.addTab(proxy_tab, get_icon("network-vpn"), "Proxy")

        # ── Startup ──
        startup_tab = QWidget()
        startup_layout = QVBoxLayout(startup_tab)
        startup_layout.setSpacing(10)
        startup_layout.setContentsMargins(12, 12, 12, 12)

        startup_group = QGroupBox("Startup Settings")
        startup_group_layout = QVBoxLayout(startup_group)

        self.run_on_startup = QCheckBox("Run FelfelDM on system startup")
        self.run_on_startup.setChecked(settings.get("run_on_startup", False))
        self.run_on_startup.toggled.connect(self._on_startup_toggled)
        startup_group_layout.addWidget(self.run_on_startup)

        self.start_minimized = QCheckBox("Start minimized to system tray")
        self.start_minimized.setChecked(settings.get("start_minimized", False))
        startup_group_layout.addWidget(self.start_minimized)

        self.startup_status = QLabel("")
        self.startup_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        startup_group_layout.addWidget(self.startup_status)

        startup_layout.addWidget(startup_group)
        startup_layout.addStretch()
        tabs.addTab(startup_tab, get_icon("applications-system"), "Startup")

        # ── Service ──
        service_tab = QWidget()
        service_layout = QVBoxLayout(service_tab)
        service_layout.setSpacing(10)
        service_layout.setContentsMargins(12, 12, 12, 12)

        service_group = QGroupBox("Background Service")
        service_group_layout = QVBoxLayout(service_group)

        self.run_as_service = QCheckBox(
            "Run as background service (auto-start on login)"
        )
        self.run_as_service.setChecked(settings.get("run_as_service", False))
        self.run_as_service.toggled.connect(self._on_service_toggle)
        service_group_layout.addWidget(self.run_as_service)

        self.service_status = QLabel("")
        self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        service_group_layout.addWidget(self.service_status)

        service_layout.addWidget(service_group)
        service_layout.addStretch()
        tabs.addTab(service_tab, get_icon("applications-system"), "Service")

        # ── Notifications ──
        notif_tab = QWidget()
        notif_layout = QVBoxLayout(notif_tab)
        notif_layout.setSpacing(10)
        notif_layout.setContentsMargins(12, 12, 12, 12)

        notif_group = QGroupBox("Download Completion Sound")
        notif_group_layout = QVBoxLayout(notif_group)

        self.sound_enabled_cb = QCheckBox("Play sound when download completes")
        self.sound_enabled_cb.setChecked(settings.get("sound_enabled", True))
        notif_group_layout.addWidget(self.sound_enabled_cb)

        sound_file_row = QHBoxLayout()
        sound_file_row.setSpacing(6)
        sound_file_row.addWidget(QLabel("Sound file:"))

        self.sound_path_edit = QLineEdit()
        self.sound_path_edit.setPlaceholderText("Select a sound file...")
        self.sound_path_edit.setText(settings.get("sound_path", ""))
        self.sound_path_edit.setEnabled(self.sound_enabled_cb.isChecked())
        sound_file_row.addWidget(self.sound_path_edit)

        self.sound_browse_btn = QPushButton("📂 Browse")
        self.sound_browse_btn.clicked.connect(self._browse_sound_file)
        self.sound_browse_btn.setEnabled(self.sound_enabled_cb.isChecked())
        sound_file_row.addWidget(self.sound_browse_btn)

        self.sound_play_btn = QPushButton("▶ Play Test")
        self.sound_play_btn.clicked.connect(self._play_test_sound)
        self.sound_play_btn.setEnabled(self.sound_enabled_cb.isChecked())
        sound_file_row.addWidget(self.sound_play_btn)

        notif_group_layout.addLayout(sound_file_row)

        info_label = QLabel("Supported formats: WAV, MP3, OGG, FLAC")
        info_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        notif_group_layout.addWidget(info_label)

        notif_layout.addWidget(notif_group)
        notif_layout.addStretch()
        tabs.addTab(notif_tab, get_icon("applications-multimedia"), "Notifications")

        main_layout.addWidget(tabs)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

        self._update_proxy_status()
        self._update_service_status()

    def _open_rules_dialog(self):
        from ui.rules_dialog import RulesDialog

        if not hasattr(self._main_window, "store"):
            return

        dlg = RulesDialog(
            rule_engine=self._main_window.store.rule_engine,
            queues=self._main_window.store.queues,
            parent=self,
        )
        dlg.exec()
        self._main_window.store.save()

    def _toggle_global_speed(self, checked):
        self.global_speed_spin.setEnabled(checked)

    def _browse_sound_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sound File",
            "",
            "Sound Files (*.wav *.mp3 *.ogg *.flac);;All Files (*)",
        )
        if file_path:
            self.sound_path_edit.setText(file_path)

    def _play_test_sound(self):
        sound_path = self.sound_path_edit.text().strip()
        if not sound_path or not os.path.exists(sound_path):
            QMessageBox.warning(self, "Error", "Sound file not found!")
            return

        try:
            from PyQt6.QtMultimedia import QSound

            QSound.play(sound_path)
            return
        except ImportError:
            pass

        try:
            players = [
                ["paplay", sound_path],
                ["aplay", sound_path],
                ["ffplay", "-nodisp", "-autoexit", sound_path],
                ["mpv", "--no-video", sound_path],
            ]
            for player in players:
                try:
                    subprocess.Popen(
                        player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    return
                except FileNotFoundError:
                    continue
        except Exception:
            pass

        QMessageBox.warning(self, "Error", "Could not play sound.")

    def _update_proxy_status(self):
        from core.proxy_manager import ProxyManager

        proxy_mgr = ProxyManager(
            self._main_window.store if hasattr(self._main_window, "store") else None
        )

        if (
            proxy_mgr.global_proxy
            and proxy_mgr.global_proxy.enabled
            and proxy_mgr.global_proxy.host
        ):
            self.proxy_status_label.setText(
                f"✓ {proxy_mgr.global_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60;")
            self.proxy_info_label.setText(
                f"{proxy_mgr.global_proxy.type.value.upper()} • {proxy_mgr.global_proxy.host}:{proxy_mgr.global_proxy.port}"
            )
        else:
            self.proxy_status_label.setText("Disabled")
            self.proxy_status_label.setStyleSheet("color: #95a5a6;")
            self.proxy_info_label.setText("No global proxy configured")

    def _configure_global_proxy(self):
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyManager, ProxyConfig

        if not hasattr(self._main_window, "store"):
            QMessageBox.warning(self, "Error", "Data store not available")
            return

        proxy_mgr = ProxyManager(self._main_window.store)
        current_config = proxy_mgr.global_proxy or ProxyConfig()

        dlg = ProxyDialog(current_config, self, "Global Proxy Settings")
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            proxy_mgr.set_global_proxy(new_config)
            self._update_proxy_status()

            if hasattr(self._main_window, "aria2"):
                self._main_window.aria2.set_global_proxy(new_config)

            QMessageBox.information(self, "Success", "Proxy settings applied!")

    def _update_service_status(self):
        QTimer.singleShot(100, self._check_service_status)

    def _check_service_status(self):
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "felfeldm.service"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            is_active = result.stdout.strip() == "active"

            result2 = subprocess.run(
                ["systemctl", "--user", "is-enabled", "felfeldm.service"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            is_enabled = result2.stdout.strip() == "enabled"

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            port_open = sock.connect_ex(("localhost", 8765)) == 0
            sock.close()

            if is_active and is_enabled and port_open:
                self.service_status.setText("✓ Service is active")
                self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
            elif is_active:
                self.service_status.setText("Service is active but not enabled")
                self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            else:
                self.service_status.setText("Service is stopped")
                self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        except Exception:
            self.service_status.setText("Service is stopped")
            self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")

    def _on_service_toggle(self, checked):
        if checked:
            self.service_status.setText("Installing service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            QTimer.singleShot(100, self._install_service_async)
        else:
            self.service_status.setText("Stopping service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            QTimer.singleShot(100, self._stop_service_async)

    def _install_service_async(self):
        try:
            result = subprocess.run(
                ["which", "FelfelDM"], capture_output=True, text=True
            )
            exe_path = (
                result.stdout.strip() if result.returncode == 0 else "/usr/bin/FelfelDM"
            )

            if not os.path.exists(exe_path):
                exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "/usr/bin/FelfelDM"

            self._free_port(8765)

            service_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(service_dir, exist_ok=True)

            service_content = f"""[Unit]
Description=FelfelDM Download Manager Service
After=network.target

[Service]
Type=simple
ExecStart={exe_path} --daemon
Restart=on-failure
RestartSec=10
TimeoutStopSec=3
WorkingDirectory=/usr/share/felfeldm
StandardOutput=journal
StandardError=journal
KillMode=process
KillSignal=SIGTERM

[Install]
WantedBy=default.target
"""

            service_path = os.path.join(service_dir, "felfeldm.service")
            with open(service_path, "w") as f:
                f.write(service_content)

            subprocess.Popen(
                ["systemctl", "--user", "daemon-reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "enable", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "start", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            QTimer.singleShot(1500, self._check_service_status)
            self.service_status.setText("✓ Service installed and running")
            self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

        except Exception as e:
            self.service_status.setText(f"Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

    def _stop_service_async(self):
        try:
            subprocess.Popen(
                ["systemctl", "--user", "stop", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "disable", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "daemon-reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "reset-failed"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            QTimer.singleShot(1000, self._check_service_status)
            self.service_status.setText("Service stopped")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

        except Exception as e:
            self.service_status.setText(f"Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

    def _free_port(self, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result != 0:
                return True

            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                pids = result.stdout.strip().split("\n")
                current_pid = str(os.getpid())

                for pid in pids:
                    if pid and pid.isdigit() and pid != current_pid:
                        subprocess.Popen(
                            ["kill", "-9", pid],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )

                time.sleep(1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def get_settings(self):
        speed_limit = (
            self.global_speed_spin.value()
            if self.global_speed_enabled.isChecked()
            else 0
        )
        return {
            "aria2_host": self.host.text().strip(),
            "aria2_port": self.port.value(),
            "aria2_secret": self.secret.text(),
            "connections": self.conns.value(),
            "max_retry_attempts": self.max_retry_attempts.value(),
            "max_tries": self.max_tries.value(),
            "max_concurrent": self.max_concurrent.value(),
            "auto_clear_completed": self.auto_clear_completed.isChecked(),
            "theme": self.theme_combo.currentText().lower(),
            "run_as_service": self.run_as_service.isChecked(),
            "speed_limit": speed_limit,
            "retry_delay": self.retry_delay.value(),
            "retry_reset_after": self.retry_reset_after.value(),
            "run_on_startup": self.run_on_startup.isChecked(),
            "start_minimized": self.start_minimized.isChecked(),
            "sound_enabled": self.sound_enabled_cb.isChecked(),
            "sound_path": self.sound_path_edit.text().strip(),
            "disable_ssl_verify": self.disable_ssl_verify.isChecked(),
        }

    def _on_startup_toggled(self, checked: bool):
        if checked:
            self._add_to_startup()
        else:
            self._remove_from_startup()

        if checked:
            self.startup_status.setText("✓ Added to startup")
            self.startup_status.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.startup_status.setText("Removed from startup")
            self.startup_status.setStyleSheet("color: #95a5a6; font-size: 11px;")

    def _add_to_startup(self):
        try:
            app_path = os.path.abspath("main.py")
            desktop_file = os.path.expanduser("~/.config/autostart/felfeldm.desktop")

            os.makedirs(os.path.dirname(desktop_file), exist_ok=True)

            icon_path = os.path.abspath("logo/icon512.png")
            if not os.path.exists(icon_path):
                icon_path = "/usr/share/icons/hicolor/512x512/apps/felfeldm.png"

            content = f"""[Desktop Entry]
    Type=Application
    Name=FelfelDM
    Comment=Download Manager
    Exec=python3 {app_path}
    Icon={icon_path}
    Terminal=false
    Hidden=false
    X-GNOME-Autostart-enabled=true
    """
            with open(desktop_file, "w") as f:
                f.write(content)

            print(f"✅ Added to startup: {desktop_file}")

        except Exception as e:
            print(f"⚠️ Could not add to startup: {e}")
            self.startup_status.setText(f"Failed: {e}")
            self.startup_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_on_startup.setChecked(False)

    def _remove_from_startup(self):
        try:
            desktop_file = os.path.expanduser("~/.config/autostart/felfeldm.desktop")
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
                print(f"✅ Removed from startup: {desktop_file}")
        except Exception as e:
            print(f"⚠️ Could not remove from startup: {e}")


# ═══════════════════════════════════════════════════════════════════
# Progress / Proxy / Shutdown / Delete dialogs
# ═══════════════════════════════════════════════════════════════════


class DownloadProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)
    cancel_with_delete_requested = pyqtSignal(str)
    speed_limit_changed = pyqtSignal(str, int)

    def __init__(self, gid, dl_data, parent=None, main_window=None):
        super().__init__(parent)
        self.gid = gid

        self._main_window = main_window
        name = dl_data.get("name", "Download")
        self.setWindowTitle(name if name else "Download Progress")
        self.setMinimumSize(560, 380)
        self.setAcceptDrops(True)
        # self.resize(620, 420)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)

        self._status = "unknown"
        self._is_complete = False
        self._file_path = None

        from utils.style import detect_system_theme

        self._is_dark = detect_system_theme()

        # Status → progress bar color
        if self._is_dark:
            self._progress_colors = {
                "active": "#89b4fa",
                "downloading": "#89b4fa",
                "waiting": "#a6adc8",
                "paused": "#f9e2af",
                "complete": "#4ade80",
                "completed": "#4ade80",
                "error": "#f38ba8",
                "retrying": "#f9e2af",
                "removed": "#6c7086",
            }
        else:
            self._progress_colors = {
                "active": "#1a5fb4",
                "downloading": "#1a5fb4",
                "waiting": "#4a4a5a",
                "paused": "#b8870a",
                "complete": "#22c55e",
                "completed": "#22c55e",
                "error": "#c01c28",
                "retrying": "#b8870a",
                "removed": "#6a6a7a",
            }

        self._status_texts = {
            "active": "Downloading",
            "downloading": "Downloading",
            "waiting": "Waiting",
            "paused": "Paused",
            "complete": "Completed",
            "completed": "Completed",
            "error": "Failed",
            "retrying": "Retrying…",
            "removed": "Removed",
        }

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(False)
        main_layout.addWidget(self.tabs, 1)

        # ── Tab 1: General ──
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setContentsMargins(16, 14, 16, 14)
        general_layout.setSpacing(10)

        self.name_lbl = QLabel(dl_data.get("name", "Unknown"))
        self.name_lbl.setWordWrap(True)
        f = self.name_lbl.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.name_lbl.setFont(f)
        general_layout.addWidget(self.name_lbl)

        general_layout.addSpacing(4)

        # Details card
        self.details_card = QFrame()
        self.details_card.setObjectName("details_card")
        self.details_card.setFrameShape(QFrame.Shape.NoFrame)

        card_layout = QVBoxLayout(self.details_card)
        card_layout.setContentsMargins(12, 8, 12, 10)
        card_layout.setSpacing(6)

        card_title = QLabel("Details")
        f = card_title.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize() - 1, 9))
        card_title.setFont(f)
        card_layout.addWidget(card_title)

        self.info_labels = {}

        info_grid = QGridLayout()
        info_grid.setSpacing(6)
        info_grid.setHorizontalSpacing(18)
        info_grid.setColumnStretch(1, 1)
        info_grid.setContentsMargins(0, 4, 0, 0)

        rows = [
            ("Size:", "size"),
            ("Downloaded:", "downloaded"),
            ("Speed:", "speed"),
            ("Time left:", "eta"),
            ("Connections:", "connections"),
            ("Proxy:", "proxy"),
        ]

        for i, (label_text, key) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setEnabled(False)
            info_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignTop)

            if key == "speed":
                speed_wrap = QWidget()
                sw = QHBoxLayout(speed_wrap)
                sw.setContentsMargins(0, 0, 0, 0)
                sw.setSpacing(8)

                val_lbl = QLabel("—")
                f = val_lbl.font()
                f.setBold(True)
                val_lbl.setFont(f)
                sw.addWidget(val_lbl)

                self._speed_limit_badge = QLabel("")
                self._speed_limit_badge.setVisible(False)
                sw.addWidget(self._speed_limit_badge)
                sw.addStretch()

                info_grid.addWidget(speed_wrap, i, 1)
                self.info_labels[key] = val_lbl
            else:
                val_lbl = QLabel("—")
                f = val_lbl.font()
                f.setBold(True)
                val_lbl.setFont(f)
                val_lbl.setWordWrap(True)
                val_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                info_grid.addWidget(val_lbl, i, 1)
                self.info_labels[key] = val_lbl

        card_layout.addLayout(info_grid)
        general_layout.addWidget(self.details_card)

        # Error banner
        self.error_banner = QFrame()
        self.error_banner.setObjectName("error_banner")
        self.error_banner.setFrameShape(QFrame.Shape.NoFrame)
        self.error_banner.setVisible(False)
        err_layout = QVBoxLayout(self.error_banner)
        err_layout.setContentsMargins(10, 8, 10, 8)
        err_layout.setSpacing(2)

        err_header = QHBoxLayout()
        err_header.setSpacing(6)
        err_icon = QLabel()
        err_icon.setPixmap(get_icon("dialog-warning").pixmap(14, 14))
        err_header.addWidget(err_icon)
        self.error_title_lbl = QLabel("Failed")
        f = self.error_title_lbl.font()
        f.setBold(True)
        self.error_title_lbl.setFont(f)
        err_header.addWidget(self.error_title_lbl)
        err_header.addStretch()
        err_layout.addLayout(err_header)

        self.error_reason_lbl = QLabel("")
        self.error_reason_lbl.setWordWrap(True)
        err_layout.addWidget(self.error_reason_lbl)

        self.error_retry_lbl = QLabel("")
        self.error_retry_lbl.setEnabled(False)
        f = self.error_retry_lbl.font()
        f.setPointSize(max(f.pointSize() - 1, 9))
        self.error_retry_lbl.setFont(f)
        err_layout.addWidget(self.error_retry_lbl)

        general_layout.addWidget(self.error_banner)
        general_layout.addStretch()

        # Progress bar (bottom)
        general_layout.addSpacing(6)

        self.progress_bar = StripedProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(16)
        general_layout.addWidget(self.progress_bar)

        progress_info = QHBoxLayout()
        progress_info.setContentsMargins(0, 4, 0, 0)

        self.percent_lbl = QLabel("0%")
        f = self.percent_lbl.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.percent_lbl.setFont(f)
        progress_info.addWidget(self.percent_lbl)

        progress_info.addStretch()

        self.size_inline_lbl = QLabel("— / —")
        f = self.size_inline_lbl.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.size_inline_lbl.setFont(f)
        progress_info.addWidget(self.size_inline_lbl)

        general_layout.addLayout(progress_info)

        self.tabs.addTab(general_tab, "General")

        # ── Tab 2: Speed Limit ──
        speed_tab = QWidget()
        speed_tab_layout = QVBoxLayout(speed_tab)
        speed_tab_layout.setContentsMargins(16, 14, 16, 14)
        speed_tab_layout.setSpacing(10)

        speed_title = QLabel("Per-download speed limit")
        f = speed_title.font()
        f.setBold(True)
        speed_title.setFont(f)
        speed_tab_layout.addWidget(speed_title)

        speed_input_row = QHBoxLayout()
        speed_input_row.setSpacing(8)
        speed_input_row.addWidget(QLabel("Limit:"))

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 999999)
        self.speed_limit_spin.setSuffix(" KB/s")
        self.speed_limit_spin.setMinimumWidth(140)
        self.speed_limit_spin.setFixedHeight(30)
        speed_input_row.addWidget(self.speed_limit_spin)

        self.speed_limit_btn = QPushButton(get_icon("dialog-ok-apply"), "Apply")
        self.speed_limit_btn.setFixedHeight(30)
        self.speed_limit_btn.setMinimumWidth(100)
        self.speed_limit_btn.clicked.connect(self._on_apply_speed_limit)
        speed_input_row.addWidget(self.speed_limit_btn)

        speed_input_row.addStretch()
        speed_tab_layout.addLayout(speed_input_row)

        self.speed_status_lbl = QLabel("")
        self.speed_status_lbl.setWordWrap(True)
        self.speed_status_lbl.setMargin(8)
        speed_tab_layout.addWidget(self.speed_status_lbl)

        speed_hint = QLabel(
            "Set to <b>0</b> for unlimited speed. "
            "A per-download limit overrides the queue and global limits."
        )
        speed_hint.setWordWrap(True)
        if self._is_dark:
            speed_hint.setStyleSheet("color: #a6adc8;")
        else:
            speed_hint.setStyleSheet("color: #4a4a5a;")
        speed_tab_layout.addWidget(speed_hint)

        speed_tab_layout.addStretch()

        self.tabs.addTab(speed_tab, "Speed Limit")

        # ── Tab 3: Technical ──
        tech_tab = QWidget()
        tech_layout = QVBoxLayout(tech_tab)
        tech_layout.setContentsMargins(14, 14, 14, 14)
        tech_layout.setSpacing(8)

        self.tech_label = QPlainTextEdit()
        self.tech_label.setReadOnly(True)
        self.tech_label.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        mono.setPointSize(9)
        self.tech_label.setFont(mono)
        self.tech_label.setPlaceholderText(
            "No technical details available for this download."
        )
        tech_layout.addWidget(self.tech_label)

        copy_row = QHBoxLayout()
        copy_row.addStretch()
        self.copy_tech_btn = QPushButton(get_icon("edit-copy"), "Copy")
        self.copy_tech_btn.setFixedHeight(28)
        self.copy_tech_btn.setMinimumWidth(90)
        self.copy_tech_btn.clicked.connect(self._on_copy_technical)
        copy_row.addWidget(self.copy_tech_btn)
        tech_layout.addLayout(copy_row)

        self.tabs.addTab(tech_tab, "Technical")

        # Legacy hidden labels — keep info_labels["status"] and ["path"]
        self._legacy_container = QWidget()
        self._legacy_container.setVisible(False)
        legacy_layout = QGridLayout(self._legacy_container)
        for key in ("status", "path"):
            lbl = QLabel("—")
            legacy_layout.addWidget(lbl)
            self.info_labels[key] = lbl
        main_layout.addWidget(self._legacy_container)

        # Action bar
        action_bar = QFrame()
        action_bar.setObjectName("action_bar")
        action_bar.setFrameShape(QFrame.Shape.NoFrame)
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(14, 10, 14, 12)
        action_layout.setSpacing(10)

        self.action_btn = QPushButton()
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText("Pause")
        self.action_btn.setMinimumWidth(110)
        self.action_btn.setFixedHeight(32)
        self.action_btn.clicked.connect(self._on_action_clicked)
        action_layout.addWidget(self.action_btn)

        action_layout.addStretch()

        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(get_icon("edit-delete"))
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        action_layout.addWidget(self.cancel_btn)

        main_layout.addWidget(action_bar)

        self._apply_styles()

        if dl_data:
            files = dl_data.get("files", [])
            if files and files[0].get("path"):
                self._file_path = files[0]["path"]
            self.update_data(dl_data)

    def _apply_styles(self):
        self.details_card.setStyleSheet("""
            QFrame#details_card {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(alternate-base);
            }
        """)

        self.error_banner.setStyleSheet("""
            QFrame#error_banner {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(alternate-base);
            }
        """)

        action_bar = self.findChild(QFrame, "action_bar")
        if action_bar:
            action_bar.setStyleSheet("""
                QFrame#action_bar {
                    border-top: 1px solid palette(mid);
                }
            """)

        if self._is_dark:
            tab_text = "#cdd6f4"
            tab_text_dim = "#7f849c"
            tab_text_hover = "#cdd6f4"
            tab_accent = "#89b4fa"
            pane_border = "#45475a"
        else:
            tab_text = "#1e1e2a"
            tab_text_dim = "#6c7086"
            tab_text_hover = "#1e1e2a"
            tab_accent = "#1a5fb4"
            pane_border = "#c0c0c8"

        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                border-top: 1px solid {pane_border};
                background: transparent;
                top: -1px;
            }}
            QTabBar {{
                background: transparent;
            }}
            QTabBar::tab {{
                padding: 7px 16px;
                margin-right: 2px;
                border: none;
                background: transparent;
                color: {tab_text_dim};
                font-size: 12px;
            }}
            QTabBar::tab:hover {{
                color: {tab_text_hover};
            }}
            QTabBar::tab:selected {{
                color: {tab_text};
                border-bottom: 2px solid {tab_accent};
                font-weight: bold;
            }}
        """)

    def set_gid(self, new_gid: str) -> None:
        self.gid = new_gid
        self._is_complete = False
        self._status = "active"
        self.setWindowTitle("Download Progress")

    def _on_apply_speed_limit(self):
        value = self.speed_limit_spin.value()
        self.speed_limit_changed.emit(self.gid, value)

    def _update_speed_status_banner(self, current_limit: int):
        dim_color = "#a6adc8" if self._is_dark else "#4a4a5a"

        if current_limit > 0:
            self.speed_status_lbl.setText(
                f"⚡ <b>Current limit:</b> {current_limit} KB/s<br>"
                f"<span style='color: {dim_color};'>"
                "This overrides the queue and global limits for this download."
                "</span>"
            )
        else:
            self.speed_status_lbl.setText(
                "ℹ️ <b>No per-download limit.</b><br>"
                f"<span style='color: {dim_color};'>"
                "Using the queue limit (or the global limit if the queue has none)."
                "</span>"
            )

    def _update_speed_badge(self, current_limit: int):
        if self._speed_limit_badge is None:
            return
        if current_limit > 0:
            self._speed_limit_badge.setText(f"⚡ {current_limit} KB/s")
            self._speed_limit_badge.setVisible(True)
        else:
            self._speed_limit_badge.setVisible(False)

    def _on_copy_technical(self):
        QApplication.clipboard().setText(self.tech_label.toPlainText())
        self.copy_tech_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_tech_btn.setText("Copy"))

    def _on_action_clicked(self):
        if self._is_complete:
            folder_path = None

            if self._file_path and os.path.exists(self._file_path):
                folder_path = os.path.dirname(self._file_path)

            if not folder_path and self._main_window is not None:
                try:
                    folder_path = self._main_window._find_download_folder(self.gid)
                except Exception:
                    pass

            if not folder_path:
                folder_path = os.path.expanduser("~/Downloads")

            if folder_path and os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                QMessageBox.warning(
                    self, "Folder Not Found", f"Folder not found:\n{folder_path}"
                )
            return

        btn_text = self.action_btn.text().strip()
        if btn_text == "Pause":
            self.pause_requested.emit(self.gid)
        elif btn_text in ["Resume", "Start", "Retry"]:
            self.resume_requested.emit(self.gid)

    def _on_cancel_clicked(self):
        if self._is_complete:
            self.close()
            return

        reply = QMessageBox.question(
            self,
            "Cancel Download",
            "Cancel this download?\n\nDo you also want to delete downloaded files?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        elif reply == QMessageBox.StandardButton.Yes:
            self.cancel_with_delete_requested.emit(self.gid)
            self.close()
        else:
            self.cancel_requested.emit(self.gid)
            self.close()

    def update_data(self, dl_data):
        from utils.helpers import format_size, format_speed

        if not dl_data:
            return

        total = int(dl_data.get("totalLength", 0))
        completed = int(dl_data.get("completedLength", 0))
        speed = int(dl_data.get("downloadSpeed", 0))
        status = dl_data.get("status", "unknown")
        name = dl_data.get("name", "")

        files = dl_data.get("files", [])
        if files and files[0].get("path"):
            self._file_path = files[0]["path"]

        if status == "complete" and not self._is_complete:
            self._is_complete = True
            self.setWindowTitle(f"✅ {name}" if name else "Download Completed!")
            self.show()
            self.raise_()
            self.activateWindow()

        if name:
            self.name_lbl.setText(name)
            if not self._is_complete:
                self.setWindowTitle(name)

        # Progress bar
        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(min(pct, 100))
            self.percent_lbl.setText(f"{pct}%")
            self.size_inline_lbl.setText(
                f"{format_size(completed)} / {format_size(total)}"
            )
        else:
            self.progress_bar.setValue(0)
            self.percent_lbl.setText("—")
            self.size_inline_lbl.setText(f"{format_size(completed)} / Unknown")

        # Progress bar style
        chunk_color = self._progress_colors.get(status, "#888")

        if status == "paused":
            if self._is_dark:
                stripe_color = "#ffb700"
                base_color = "#ffd93d"
            else:
                stripe_color = "#e69a00"
                base_color = "#f5b400"

            self.progress_bar.set_color(base_color)
            self.progress_bar.set_striped(True, stripe_color=stripe_color)
        else:
            self.progress_bar.set_color(chunk_color)
            self.progress_bar.set_striped(False)

        # Info grid
        self.info_labels["size"].setText(format_size(total) if total > 0 else "Unknown")
        self.info_labels["downloaded"].setText(format_size(completed))

        if status == "paused":
            speed_str = "0 B/s"
        elif status == "complete":
            speed_str = "Done"
        elif status == "error":
            speed_str = "—"
        else:
            speed_str = format_speed(speed) if speed > 0 else "—"

        self.info_labels["speed"].setText(speed_str)

        eta_str = "—"
        if (
            status not in ("paused", "complete", "error")
            and speed > 0
            and total > completed
        ):
            eta_sec = (total - completed) // speed
            h, m, s = eta_sec // 3600, (eta_sec % 3600) // 60, eta_sec % 60
            if h > 0:
                eta_str = f"{h}h {m:02d}m"
            elif m > 0:
                eta_str = f"{m}m {s:02d}s"
            else:
                eta_str = f"{s}s"

        self.info_labels["eta"].setText(eta_str)

        self.info_labels["connections"].setText(str(dl_data.get("connections", 0)))

        # Proxy
        proxy_url = dl_data.get("proxy_url", "")
        if proxy_url and proxy_url.strip():
            self.info_labels["proxy"].setText(proxy_url)
        else:
            self.info_labels["proxy"].setText("—")

        # Error banner
        from utils.helpers import get_error_reason, get_retry_status

        if status in ("error", "retrying"):
            reason = get_error_reason(dl_data.get("errorMessage", ""))
            retry = get_retry_status(dl_data)
            self.error_reason_lbl.setText(reason)
            self.error_retry_lbl.setText(f"Retry: {retry}")
            self.error_banner.setVisible(True)
        else:
            self.error_banner.setVisible(False)

        # Hidden legacy labels
        display_text = self._status_texts.get(status, status.capitalize())
        self.info_labels["status"].setText(display_text)
        if self._file_path:
            self.info_labels["path"].setText(self._file_path)
        else:
            self.info_labels["path"].setText("—")

        # Speed badge
        current_limit = dl_data.get("speed_limit", 0)
        self._update_speed_badge(current_limit)

        # Speed limit tab
        if not self.speed_limit_spin.hasFocus():
            if current_limit != self.speed_limit_spin.value():
                self.speed_limit_spin.blockSignals(True)
                self.speed_limit_spin.setValue(current_limit)
                self.speed_limit_spin.blockSignals(False)

        self._update_speed_status_banner(current_limit)

        # Technical tab
        tech_lines = []
        tech_lines.append("Download")
        tech_lines.append(f"  Download ID      {self.gid}")
        tech_lines.append(f"  Status           {status}")
        if dl_data.get("aria2_gid"):
            tech_lines.append(f"  aria2 GID        {dl_data.get('aria2_gid')}")
        tech_lines.append(f"  Connections      {dl_data.get('connections', 0)}")

        # Proxy info
        proxy_url = dl_data.get("proxy_url", "")
        if proxy_url and proxy_url.strip():
            tech_lines.append(f"  Proxy            {proxy_url}")

        if self._file_path:
            tech_lines.append("")
            tech_lines.append("File")
            tech_lines.append(f"  Path             {self._file_path}")
        if total > 0:
            tech_lines.append(f"  Size             {total} bytes")

        raw_error = dl_data.get("errorMessage", "").strip()
        if raw_error:
            tech_lines.append("")
            tech_lines.append("Error")
            tech_lines.append(f"  {raw_error}")

        new_text = "\n".join(tech_lines)
        if self.tech_label.toPlainText() != new_text:
            scrollbar = self.tech_label.verticalScrollBar()
            old_scroll = scrollbar.value()
            self.tech_label.setPlainText(new_text)
            scrollbar.setValue(old_scroll)

        self._status = status
        self._update_buttons(status)

    def _update_buttons(self, status):
        if status == "complete":
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText("Open Folder")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            self.cancel_btn.setEnabled(True)
        elif status == "active":
            self.action_btn.setIcon(get_icon("media-playback-pause"))
            self.action_btn.setText("Pause")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        elif status in ["paused", "waiting"]:
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Resume")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        elif status == "error":
            self.action_btn.setIcon(get_icon("view-refresh"))
            self.action_btn.setText("Retry")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        elif status == "retrying":
            self.action_btn.setEnabled(False)
            self.action_btn.setText("Retrying…")
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        else:
            self.action_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)


class ProxyDialog(QDialog):
    def __init__(
        self, proxy_config: ProxyConfig = None, parent=None, title="Proxy Settings"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setMinimumHeight(200)
        self.setSizeGripEnabled(True)

        self.proxy_config = proxy_config or ProxyConfig()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        self.enable_cb = QCheckBox("Enable Proxy")
        self.enable_cb.setChecked(self.proxy_config.enabled)
        self.enable_cb.toggled.connect(self._toggle_enable)
        main_layout.addWidget(self.enable_cb)

        form_group = QGroupBox("Proxy Configuration")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(6)

        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value.upper() for t in ProxyType])
        current_type = self.proxy_config.type.value.upper()
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        form_layout.addRow("Type:", self.type_combo)

        self.host_edit = QLineEdit(self.proxy_config.host)
        self.host_edit.setPlaceholderText("proxy.example.com or 127.0.0.1")
        form_layout.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.proxy_config.port)
        form_layout.addRow("Port:", self.port_spin)

        auth_label = QLabel("Authentication (optional)")
        auth_label.setStyleSheet("font-weight: 500; margin-top: 4px;")
        form_layout.addRow(auth_label)

        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username")
        form_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")
        form_layout.addRow("Password:", self.password_edit)

        main_layout.addWidget(form_group)

        test_btn = QPushButton(get_icon("view-refresh"), "Test Proxy Connection")
        test_btn.clicked.connect(self._test_proxy)
        main_layout.addWidget(test_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        main_layout.addWidget(self.status_label)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

        self._toggle_enable(self.proxy_config.enabled)

    def _toggle_enable(self, checked):
        self.type_combo.setEnabled(checked)
        self.host_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)
        self.username_edit.setEnabled(checked)
        self.password_edit.setEnabled(checked)

    def _test_proxy(self):
        config = self.get_proxy_config()
        if not config.is_valid():
            self.status_label.setText("Invalid proxy configuration")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return

        try:
            import requests

            proxy_url = config._build_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}

            self.status_label.setText("Testing connection...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()

            response = requests.get(
                "https://www.google.com", proxies=proxies, timeout=10
            )

            if response.status_code == 200:
                self.status_label.setText("Proxy is working!")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(f"Status: {response.status_code}")
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")

        except requests.exceptions.Timeout:
            self.status_label.setText("Connection timeout")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.ConnectionError:
            self.status_label.setText("Connection failed")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def get_proxy_config(self) -> ProxyConfig:
        type_str = self.type_combo.currentText().lower()
        proxy_type = ProxyType(type_str)

        return ProxyConfig(
            proxy_type=proxy_type,
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text().strip() or None,
            enabled=self.enable_cb.isChecked(),
        )


class ShutdownCountdownDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Shutdown")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(380)
        self.setMinimumHeight(220)

        self._countdown = 20
        self._timer = None
        self._cancelled = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(25, 20, 25, 20)

        title = QLabel("⚠️ System Shutdown")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; ")
        main_layout.addWidget(title)

        msg = QLabel("All downloads are complete!\nThe system will shut down in:")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("font-size: 13px; ")
        main_layout.addWidget(msg)

        self.countdown_lbl = QLabel("20")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_lbl.setStyleSheet("font-size: 52px; font-weight: bold;")
        main_layout.addWidget(self.countdown_lbl)

        self.cancel_btn = QPushButton("Cancel Shutdown")
        self.cancel_btn.setFixedHeight(36)

        self.cancel_btn.clicked.connect(self._on_cancel)
        main_layout.addWidget(self.cancel_btn)

    def start_countdown(self):
        self._countdown = 20
        self.countdown_lbl.setText("20")
        self._cancelled = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start(1000)

        self.exec()

    def _update_countdown(self):
        self._countdown -= 1
        self.countdown_lbl.setText(str(self._countdown))

        if self._countdown <= 0:
            self._timer.stop()
            self._timer = None
            self.accept()

    def _on_cancel(self):
        self._cancelled = True
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.reject()

    def is_cancelled(self):
        return self._cancelled

    def closeEvent(self, event):
        if self._timer:
            self._timer.stop()
            self._timer = None
        event.accept()


class DeleteFilesConfirmationDialog(QDialog):
    """Confirmation dialog listing which files will be deleted.

    Read-only: the user either confirms the whole list or cancels.
    """

    def __init__(self, entries: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Delete Files")
        self.setMinimumWidth(560)
        self.setMinimumHeight(360)
        self.setModal(True)

        self._entries = entries

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(20, 20, 20, 16)

        header = QLabel(f"The following <b>{len(entries)}</b> file(s) will be deleted:")
        header.setWordWrap(True)
        main_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setMinimumHeight(200)

        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setSpacing(4)
        list_layout.setContentsMargins(8, 8, 8, 8)

        for entry in entries:
            row = QHBoxLayout()
            row.setSpacing(8)

            icon_label = QLabel()
            if entry.get("kind") == "sidecar":
                icon_label.setText("📄")
            else:
                icon_label.setText("📦")
            icon_label.setFixedWidth(24)
            row.addWidget(icon_label)

            info_layout = QVBoxLayout()
            info_layout.setSpacing(1)

            name_label = QLabel(entry["name"])
            name_label.setWordWrap(True)
            if entry.get("kind") == "sidecar":
                name_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
            else:
                name_label.setStyleSheet("font-weight: 500;")
            info_layout.addWidget(name_label)

            meta_parts = []
            size = entry.get("size", 0)
            if size > 0:
                meta_parts.append(format_size(size))
            meta_parts.append(os.path.dirname(entry["path"]))
            if entry.get("kind") == "sidecar":
                meta_parts.append("(aria2 sidecar)")
            if not entry.get("exists", True):
                meta_parts.append("⚠️ already missing")

            meta_label = QLabel("  •  ".join(meta_parts))
            meta_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
            meta_label.setWordWrap(True)
            info_layout.addWidget(meta_label)

            row.addLayout(info_layout, 1)
            list_layout.addLayout(row)

        list_layout.addStretch()
        scroll.setWidget(list_widget)
        main_layout.addWidget(scroll, 1)

        total_size = sum(e.get("size", 0) for e in entries)
        existing_count = sum(1 for e in entries if e.get("exists", True))

        total_label = QLabel(
            f"<b>Total:</b> {format_size(total_size)} "
            f"across {existing_count} existing file(s)"
        )
        main_layout.addWidget(total_label)

        warning = QLabel(
            "⚠️ <b>This action cannot be undone.</b> "
            "The files will be permanently removed from disk."
        )
        warning.setStyleSheet("color: #e74c3c; padding: 6px;")
        warning.setWordWrap(True)
        main_layout.addWidget(warning)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        delete_btn = QPushButton("Delete Files")
        delete_btn.setIcon(get_icon("edit-delete"))
        delete_btn.setDefault(True)
        delete_btn.clicked.connect(self.accept)
        btn_row.addWidget(delete_btn)

        main_layout.addLayout(btn_row)

    def get_paths_to_delete(self) -> list:
        """Return all existing file paths shown in the dialog.

        Kept as a method so _delete_files_with_confirmation stays unchanged.
        """
        return [entry["path"] for entry in self._entries if entry.get("exists", True)]
