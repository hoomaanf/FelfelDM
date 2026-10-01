# ui/youtube_progress.py

import os
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QFrame,
    QTabWidget,
    QWidget,
    QGridLayout,
    QPlainTextEdit,
    QApplication,
)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal, QRect
from PyQt6.QtGui import (
    QDesktopServices,
    QColor,
    QFont,
    QPainter,
    QBrush,
    QPixmap,
    QPen
)
from core.youtube_worker import YouTubeWorker
from utils.helpers import format_size, get_icon
import tempfile


def _make_stripe_pixmap(stripe_color: str, base_color: str, width: int = 16, height: int = 16) -> QPixmap:
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
        self._stripe_pixmap = _make_stripe_pixmap(
            self._stripe_color, self._base_color
        )
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
 

class YouTubeProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)

    def __init__(
        self,
        url,
        output_path,
        format_type="mp4",
        cookie_file=None,
        video_info=None,
        parent=None,
        proxy_url=None,
        download_id=None,
    ):
        super().__init__(parent)

        title = (
            video_info.get("title", "YouTube Download")
            if video_info
            else "YouTube Download"
        )

        if (not title or title == "YouTube Download") and download_id and parent:
            if (
                hasattr(parent, "_all_downloads")
                and download_id in parent._all_downloads
            ):
                title = parent._all_downloads[download_id].get("name", title)

        self.setWindowTitle(title if title else "YouTube Download")
        self.setMinimumSize(560, 380)
        self.resize(620, 420)
        self.setSizeGripEnabled(True)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.download_id = download_id
        self.url = url
        self.output_path = output_path
        self.format_type = format_type
        self.cookie_file = cookie_file
        self.video_info = video_info
        self.proxy_url = proxy_url
        self._is_complete = False
        self._file_path = None
        self._is_paused = False
        self._progress_value = 0
        self._speed_text = ""
        self._eta_text = ""
        self._status_text = ""
        self._worker = None
        self._is_existing_download = download_id is not None

        if not self.proxy_url and hasattr(parent, "_get_proxy_url"):
            self.proxy_url = parent._get_proxy_url()

        from utils.style import detect_system_theme

        self._is_dark = detect_system_theme()

        # Progress bar colors
        if self._is_dark:
            self._progress_colors = {
                "pending": "#a6adc8",
                "downloading": "#89b4fa",
                "paused": "#f9e2af",
                "complete": "#4ade80",
                "error": "#f38ba8",
            }
        else:
            self._progress_colors = {
                "pending": "#4a4a5a",
                "downloading": "#1a5fb4",
                "paused": "#b8870a",
                "complete": "#22c55e",
                "error": "#c01c28",
            }

        self._build_ui()

        if not self._is_existing_download:
            self._create_worker()
        else:
            self._load_existing_state()

    # ═══════════════════════════════════════════════════════════
    # UI construction
    # ═══════════════════════════════════════════════════════════

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(False)
        main_layout.addWidget(self.tabs, 1)

        # ───────────────────────────────────────────────────────
        # Tab 1: Details (progress + basic info)
        # ───────────────────────────────────────────────────────
        details_tab = QWidget()
        details_layout = QVBoxLayout(details_tab)
        details_layout.setContentsMargins(16, 14, 16, 14)
        details_layout.setSpacing(10)

        # Title (video name)
        video_title = "Downloading from YouTube"
        if self.video_info:
            video_title = self.video_info.get("title", "Downloading from YouTube")

        self.title_label = QLabel(video_title)
        self.title_label.setWordWrap(True)
        f = self.title_label.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.title_label.setFont(f)
        details_layout.addWidget(self.title_label)

        details_layout.addSpacing(4)

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

        info_grid = QGridLayout()
        info_grid.setSpacing(6)
        info_grid.setHorizontalSpacing(18)
        info_grid.setColumnStretch(1, 1)
        info_grid.setContentsMargins(0, 4, 0, 0)

        rows = [
            ("Status:", "status"),
            ("Speed:", "speed"),
            ("Time left:", "eta"),
            ("Format:", "format"),
        ]

        self.info_labels = {}
        for i, (label_text, key) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setEnabled(False)
            info_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignTop)

            val_lbl = QLabel("—")
            f = val_lbl.font()
            f.setBold(True)
            val_lbl.setFont(f)
            val_lbl.setWordWrap(True)
            info_grid.addWidget(val_lbl, i, 1)
            self.info_labels[key] = val_lbl

        card_layout.addLayout(info_grid)
        details_layout.addWidget(self.details_card)
        details_layout.addStretch()

        # Progress bar (bottom)
        details_layout.addSpacing(6)

        self.progress_bar = StripedProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(16)
        details_layout.addWidget(self.progress_bar)

        # Percent (left) + speed (right)
        progress_info = QHBoxLayout()
        progress_info.setContentsMargins(0, 4, 0, 0)

        self.percent_lbl = QLabel("0%")
        f = self.percent_lbl.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.percent_lbl.setFont(f)
        progress_info.addWidget(self.percent_lbl)

        progress_info.addStretch()

        self.speed_eta_lbl = QLabel("")
        f = self.speed_eta_lbl.font()
        f.setBold(True)
        f.setPointSize(max(f.pointSize(), 11))
        self.speed_eta_lbl.setFont(f)
        progress_info.addWidget(self.speed_eta_lbl)

        details_layout.addLayout(progress_info)

        self.tabs.addTab(details_tab, "Details")

        # ───────────────────────────────────────────────────────
        # Tab 2: Video Info
        # ───────────────────────────────────────────────────────
        video_tab = QWidget()
        video_layout = QVBoxLayout(video_tab)
        video_layout.setContentsMargins(16, 14, 16, 14)
        video_layout.setSpacing(10)

        if self.video_info:
            video_card = QFrame()
            video_card.setObjectName("video_card")
            video_card.setFrameShape(QFrame.Shape.NoFrame)

            vc_layout = QVBoxLayout(video_card)
            vc_layout.setContentsMargins(12, 8, 12, 10)
            vc_layout.setSpacing(6)

            vc_title = QLabel("Video Information")
            f = vc_title.font()
            f.setBold(True)
            f.setPointSize(max(f.pointSize() - 1, 9))
            vc_title.setFont(f)
            vc_layout.addWidget(vc_title)

            v_grid = QGridLayout()
            v_grid.setSpacing(6)
            v_grid.setHorizontalSpacing(18)
            v_grid.setColumnStretch(1, 1)
            v_grid.setContentsMargins(0, 4, 0, 0)

            video_rows = []

            title = self.video_info.get("title", "Unknown")
            video_rows.append(("Title:", title))

            uploader = self.video_info.get("uploader", "Unknown")
            video_rows.append(("Channel:", uploader))

            duration = self.video_info.get("duration", 0)
            minutes = duration // 60
            seconds = duration % 60
            video_rows.append(("Duration:", f"{minutes}:{seconds:02d}"))

            resolution = self.video_info.get("resolution", "")
            if resolution:
                video_rows.append(("Quality:", resolution))

            format_names = {
                "mp4": "MP4 Video",
                "webm": "WebM Video",
                "mp3": "MP3 Audio",
                "m4a": "M4A Audio",
            }
            video_rows.append(
                ("Format:", format_names.get(self.format_type, self.format_type))
            )

            filesize = self.video_info.get("filesize")
            if filesize:
                video_rows.append(("Size:", format_size(filesize)))

            if self.proxy_url:
                video_rows.append(("Proxy:", self.proxy_url))

            for i, (label_text, value) in enumerate(video_rows):
                lbl = QLabel(label_text)
                lbl.setEnabled(False)
                v_grid.addWidget(lbl, i, 0, Qt.AlignmentFlag.AlignTop)

                val_lbl = QLabel(str(value))
                f = val_lbl.font()
                f.setBold(True)
                val_lbl.setFont(f)
                val_lbl.setWordWrap(True)
                val_lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                v_grid.addWidget(val_lbl, i, 1)

            vc_layout.addLayout(v_grid)
            video_layout.addWidget(video_card)
        else:
            no_info = QLabel("No video information available.")
            no_info.setEnabled(False)
            video_layout.addWidget(no_info)

        video_layout.addStretch()

        self.tabs.addTab(video_tab, "Video Info")

        # ───────────────────────────────────────────────────────
        # Tab 3: Technical
        # ───────────────────────────────────────────────────────
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

        # ───────────────────────────────────────────────────────
        # Action bar
        # ───────────────────────────────────────────────────────
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

        # Style
        self._apply_styles()

        # Initial values
        self.info_labels["format"].setText(
            {
                "mp4": "MP4 Video",
                "webm": "WebM Video",
                "mp3": "MP3 Audio",
                "m4a": "M4A Audio",
            }.get(self.format_type, self.format_type)
        )

        # Legacy compatibility labels (hidden, kept for existing callers)
        self.status_label = QLabel("")
        self.status_label.setVisible(False)
        self.speed_eta_label = QLabel("")
        self.speed_eta_label.setVisible(False)

        # Prime progress bar
        self._apply_progress_style("pending")

        # Fill technical tab with initial info
        self._update_technical()

    def _apply_styles(self):
        self.details_card.setStyleSheet("""
            QFrame#details_card {
                border: 1px solid palette(mid);
                border-radius: 6px;
                background: palette(alternate-base);
            }
        """)

        card = self.findChild(QFrame, "video_card")
        if card:
            card.setStyleSheet("""
                QFrame#video_card {
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

    def _apply_progress_style(self, state: str):
        """state: pending | downloading | paused | complete | error"""
        chunk_color = self._progress_colors.get(state, "#888")

        if state == "paused":
            if self._is_dark:
                stripe_color = "#ffb700"
                base_color = "#ffd93d"
            else:
                stripe_color = "#e69a00"
                base_color = "#f5b400"

            self.progress_bar.set_striped(
                True,
                base_color=base_color,
                stripe_color=stripe_color,
            )
        else:
            self.progress_bar.set_striped(False, base_color=chunk_color)

    # ═══════════════════════════════════════════════════════════
    # Technical tab
    # ═══════════════════════════════════════════════════════════

    def _update_technical(self):
        lines = []
        lines.append("Download")
        lines.append(f"  Download ID      {self.download_id or '—'}")
        lines.append(f"  Type             youtube")
        lines.append(f"  Status           {self._status_text or '—'}")
        lines.append(f"  Format           {self.format_type}")

        lines.append("")
        lines.append("Source")
        lines.append(f"  URL              {self.url}")
        lines.append(f"  Output path      {self.output_path}")

        if self.cookie_file:
            lines.append(f"  Cookies file     {self.cookie_file}")

        if self.proxy_url:
            lines.append(f"  Proxy            {self.proxy_url}")

        if self._file_path:
            lines.append("")
            lines.append("File")
            lines.append(f"  Path             {self._file_path}")

        if self.video_info:
            lines.append("")
            lines.append("Video")
            lines.append(f"  Title            {self.video_info.get('title', '—')}")
            lines.append(f"  Uploader         {self.video_info.get('uploader', '—')}")
            lines.append(f"  Duration         {self.video_info.get('duration', '—')}s")
            if self.video_info.get("resolution"):
                lines.append(f"  Resolution       {self.video_info.get('resolution')}")

        new_text = "\n".join(lines)

        if self.tech_label.toPlainText() == new_text:
            return

        # Preserve scroll position
        scrollbar = self.tech_label.verticalScrollBar()
        old_scroll = scrollbar.value()

        self.tech_label.setPlainText(new_text)

        scrollbar.setValue(old_scroll)
        
    def _on_copy_technical(self):
        QApplication.clipboard().setText(self.tech_label.toPlainText())
        self.copy_tech_btn.setText("Copied!")
        QTimer.singleShot(1500, lambda: self.copy_tech_btn.setText("Copy"))

    # ═══════════════════════════════════════════════════════════
    # State loading
    # ═══════════════════════════════════════════════════════════

    def _load_existing_state(self):
        parent = self.parent()
        info = {}
        if (
            parent
            and hasattr(parent, "_all_downloads")
            and self.download_id in parent._all_downloads
        ):
            info = parent._all_downloads[self.download_id]

        status = info.get("status", "pending")
        progress = info.get("progress", 0)
        speed = info.get("speed", "")
        eta = info.get("eta", "")

        self.update_progress(progress, speed, eta)

        if status == "pending":
            self.info_labels["status"].setText("Pending")
            self.action_btn.setEnabled(False)
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Start")
            self._apply_progress_style("pending")

        elif status == "paused":
            self.info_labels["status"].setText("Paused")
            self.action_btn.setEnabled(True)
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Resume")
            self._is_paused = True
            self._apply_progress_style("paused")

        elif status == "downloading":
            self.info_labels["status"].setText("Downloading")
            self.action_btn.setEnabled(True)
            self.action_btn.setIcon(get_icon("media-playback-pause"))
            self.action_btn.setText("Pause")
            self._is_paused = False
            self._apply_progress_style("downloading")

        elif status == "completed":
            self.info_labels["status"].setText("Completed")
            self.action_btn.setEnabled(True)
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText("Open Folder")
            self._is_complete = True
            self._apply_progress_style("complete")

        elif status == "error":
            self.info_labels["status"].setText("Failed")
            self.action_btn.setEnabled(False)
            self._apply_progress_style("error")

        self._update_technical()

    # ═══════════════════════════════════════════════════════════
    # Worker
    # ═══════════════════════════════════════════════════════════

    def _create_worker(self):
        self._worker = YouTubeWorker(
            url=self.url,
            output_path=self.output_path,
            format_type=self.format_type,
            cookie_file=self.cookie_file,
            proxy_url=self.proxy_url,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.status.connect(self._on_status)
        self._worker.speed_eta.connect(self._on_speed_eta)
        self._worker.finished.connect(self._on_finished)
        self._worker.paused.connect(self._on_paused)
        self._worker.resumed.connect(self._on_resumed)
        self._worker.start()

    # ═══════════════════════════════════════════════════════════
    # Public API (kept for compatibility with existing callers)
    # ═══════════════════════════════════════════════════════════

    def update_progress(self, progress: int, speed: str = "", eta: str = ""):
        self._progress_value = progress
        self._speed_text = speed
        self._eta_text = eta

        self.progress_bar.setValue(progress)
        self.percent_lbl.setText(f"{progress}%")

        # Right-side inline label: speed + eta
        parts = []
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"ETA {eta}")
        self.speed_eta_lbl.setText("  •  ".join(parts))

        # Update info grid
        self.info_labels["speed"].setText(speed if speed else "—")
        self.info_labels["eta"].setText(eta if eta else "—")

        if (
            not self._is_complete
            and not self._is_paused
            and progress > 0
            and progress < 100
        ):
            if not self.action_btn.isEnabled():
                self.action_btn.setEnabled(True)
                self.action_btn.setIcon(get_icon("media-playback-pause"))
                self.action_btn.setText("Pause")
                self._apply_progress_style("downloading")
                self.info_labels["status"].setText("Downloading")

    def update_status(self, status: str):
        self._status_text = status
        self.info_labels["status"].setText(status)
        self._update_technical()

    def update_finished(self, success: bool, message: str):
        self._on_finished(success, message)

    def update_pause_state(self, is_paused: bool):
        if is_paused:
            self._on_paused()
        else:
            self._on_resumed()

    def get_worker(self):
        return self._worker

    def set_action_button_enabled(self, enabled: bool):
        self.action_btn.setEnabled(enabled)
        if not enabled:
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Start")

    # ═══════════════════════════════════════════════════════════
    # Signal handlers
    # ═══════════════════════════════════════════════════════════

    def _on_progress(self, value):
        self._progress_value = value
        self.progress_bar.setValue(value)
        self.percent_lbl.setText(f"{value}%")

        if not self._is_complete and not self._is_paused:
            self.action_btn.setEnabled(True)
            self.action_btn.setIcon(get_icon("media-playback-pause"))
            self.action_btn.setText("Pause")
            self.info_labels["status"].setText("Downloading")
            self._apply_progress_style("downloading")

    def _on_status(self, text):
        self._status_text = text
        # Keep status text user-friendly
        if "Downloading" in text or "⬇" in text:
            self.info_labels["status"].setText("Downloading")
            self._apply_progress_style("downloading")
        elif "Paused" in text or "⏸" in text:
            self.info_labels["status"].setText("Paused")
            self._apply_progress_style("paused")
        elif "Complete" in text or "✅" in text:
            self.info_labels["status"].setText("Completed")
            self._apply_progress_style("complete")
        elif "Error" in text or "❌" in text:
            self.info_labels["status"].setText("Failed")
            self._apply_progress_style("error")
        self._update_technical()

    def _on_speed_eta(self, speed, eta):
        self._speed_text = speed
        self._eta_text = eta

        parts = []
        if speed:
            parts.append(speed)
        if eta:
            parts.append(f"ETA {eta}")
        self.speed_eta_lbl.setText("  •  ".join(parts))

        self.info_labels["speed"].setText(speed if speed else "—")
        self.info_labels["eta"].setText(eta if eta else "—")

    def _on_paused(self):
        self._is_paused = True
        self.action_btn.setIcon(get_icon("media-playback-start"))
        self.action_btn.setText("Resume")
        self.action_btn.setEnabled(True)
        self.info_labels["status"].setText("Paused")
        self._apply_progress_style("paused")
        self._update_technical()

    def _on_resumed(self):
        self._is_paused = False
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText("Pause")
        self.action_btn.setEnabled(True)
        self.info_labels["status"].setText("Downloading")
        self._apply_progress_style("downloading")
        self._update_technical()

    def _on_action_clicked(self):
        if self._is_complete:
            self._open_folder()
            return

        if self._is_existing_download and self.download_id:
            current_text = self.action_btn.text().strip()

            if current_text == "Resume":
                parent = self.parent()
                if parent and hasattr(parent, "_current_queue"):
                    q = parent._current_queue()
                    if q and q.paused and q.name != "__direct__":
                        QMessageBox.warning(
                            self,
                            "Queue is Paused",
                            f"The queue '{q.name}' is currently paused.\n\n"
                            "Please click the 'Start' button for this queue in the sidebar first.",
                            QMessageBox.StandardButton.Ok,
                        )
                        return
                self.resume_requested.emit(self.download_id)

            elif current_text == "Pause":
                self.pause_requested.emit(self.download_id)
            return

        if self._worker:
            current_text = self.action_btn.text().strip()
            if current_text == "Pause":
                self._worker.pause()
            else:
                self._worker.resume()

    def _on_cancel_clicked(self):
        if self._is_complete:
            self.accept()
            return

        if self._is_existing_download and self.download_id:
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Are you sure you want to cancel this download?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.cancel_requested.emit(self.download_id)
                self.info_labels["status"].setText("Cancelled")
                self.action_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)
                QTimer.singleShot(500, self.reject)
            return

        if self._worker:
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Are you sure you want to cancel this download?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self.info_labels["status"].setText("Cancelled")
                self.action_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)
                QTimer.singleShot(500, self.reject)

    def _on_finished(self, success, message):
        if success:
            self._is_complete = True
            self.title_label.setText(f"✅ {self.title_label.text()}")

            if self.video_info and self.video_info.get("title"):
                self.setWindowTitle(f"✅ {self.video_info['title']}")
            else:
                self.setWindowTitle("✅ Download completed!")

            self.info_labels["status"].setText("Completed")
            self.info_labels["speed"].setText("Done")
            self.info_labels["eta"].setText("—")
            self.speed_eta_lbl.setText("")
            self.progress_bar.setValue(100)
            self.percent_lbl.setText("100%")
            self._apply_progress_style("complete")

            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText("Open Folder")
            self.action_btn.setEnabled(True)
            try:
                self.action_btn.clicked.disconnect()
            except Exception:
                pass
            self.action_btn.clicked.connect(self._open_folder)

            self.cancel_btn.setText("Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            try:
                self.cancel_btn.clicked.disconnect()
            except Exception:
                pass
            self.cancel_btn.clicked.connect(self.accept)

            if self.video_info:
                title = self.video_info.get("title", "video")
                ext = (
                    "mp4"
                    if self.format_type == "mp4"
                    else "webm" if self.format_type == "webm" else "mp3"
                )
                safe_title = "".join(c for c in title if c.isalnum() or c in " ._-")
                self._file_path = os.path.join(self.output_path, f"{safe_title}.{ext}")

        else:
            self.title_label.setText(f"❌ {self.title_label.text()}")
            self.info_labels["status"].setText("Failed")
            self.info_labels["speed"].setText("—")
            self.info_labels["eta"].setText("—")
            self.speed_eta_lbl.setText("")
            self._apply_progress_style("error")
            self.action_btn.setEnabled(False)
            self.cancel_btn.setText("Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            try:
                self.cancel_btn.clicked.disconnect()
            except Exception:
                pass
            self.cancel_btn.clicked.connect(self.reject)

        self._update_technical()

    # ═══════════════════════════════════════════════════════════
    # Misc
    # ═══════════════════════════════════════════════════════════

    def _open_folder(self):
        if self._file_path and os.path.exists(self._file_path):
            folder = os.path.dirname(self._file_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            if os.path.exists(self.output_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_path))
            else:
                QMessageBox.warning(self, "Folder Not Found", "Folder not found.")

    def closeEvent(self, event):
        if (
            hasattr(self, "_worker")
            and self._worker
            and self._worker.isRunning()
            and not self._is_complete
        ):
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Download is in progress. Are you sure you want to cancel?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self._worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
