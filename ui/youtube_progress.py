# ui/youtube_progress.py

import os
from PyQt6.QtWidgets import (
    QDialog,
    QMessageBox,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QHBoxLayout,
    QGroupBox,
    QFormLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from core.youtube_worker import YouTubeWorker
from utils.helpers import format_size, get_icon


class YouTubeProgressDialog(QDialog):
    # ===== سیگنال‌ها برای ارتباط با MainWindow =====
    pause_requested = pyqtSignal(str)  # download_id
    resume_requested = pyqtSignal(str)  # download_id
    cancel_requested = pyqtSignal(str)  # download_id

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
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(520)

        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        # ===== ذخیره داده‌ها =====
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

        self._build_ui()

        # ===== اگر دانلود جدید هست، worker بساز =====
        if not self._is_existing_download:
            self._create_worker()
        else:
            # ===== دانلود موجود: وضعیت رو از parent بگیر =====
            self.status_label.setText("⏳ Loading...")
            self.status_label.setStyleSheet("color: #95a5a6;")

            # ===== پیش‌فرض: دکمه رو غیرفعال کن =====
            self.action_btn.setEnabled(False)
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText(" Start")

            # ===== اگر parent و _all_downloads موجوده، وضعیت رو بگیر =====
            if (
                parent
                and hasattr(parent, "_all_downloads")
                and download_id in parent._all_downloads
            ):
                status = parent._all_downloads[download_id].get("status", "pending")
                progress = parent._all_downloads[download_id].get("progress", 0)
                speed = parent._all_downloads[download_id].get("speed", "")
                eta = parent._all_downloads[download_id].get("eta", "")

                # ===== به‌روزرسانی progress =====
                self.update_progress(progress, speed, eta)

                # ===== تنظیم وضعیت =====
                if status == "pending":
                    self.status_label.setText("⏳ Pending...")
                    self.status_label.setStyleSheet("color: #f39c12;")
                    self.action_btn.setEnabled(False)
                    self.action_btn.setIcon(get_icon("media-playback-start"))
                    self.action_btn.setText(" Start")

                elif status == "paused":
                    self.status_label.setText("⏸ Paused")
                    self.status_label.setStyleSheet("color: #f39c12;")
                    self.action_btn.setEnabled(True)
                    self.action_btn.setIcon(get_icon("media-playback-start"))
                    self.action_btn.setText(" Resume")
                    self._is_paused = True

                elif status == "downloading":
                    self.status_label.setText("⬇ Downloading...")
                    self.status_label.setStyleSheet("color: #3daee9;")
                    self.action_btn.setEnabled(True)
                    self.action_btn.setIcon(get_icon("media-playback-pause"))
                    self.action_btn.setText(" Pause")
                    self._is_paused = False

                elif status == "completed":
                    self.status_label.setText("✅ Complete")
                    self.status_label.setStyleSheet("color: #27ae60;")
                    self.action_btn.setEnabled(True)
                    self.action_btn.setIcon(get_icon("folder"))
                    self.action_btn.setText(" Open Folder")
                    self._is_complete = True

                elif status == "error":
                    self.status_label.setText("❌ Error")
                    self.status_label.setStyleSheet("color: #e74c3c;")
                    self.action_btn.setEnabled(False)

            else:
                # ===== اگر parent یا _all_downloads موجود نیست =====
                self.status_label.setText("⏳ Pending...")
                self.status_label.setStyleSheet("color: #f39c12;")
                self.action_btn.setEnabled(False)
                self.action_btn.setIcon(get_icon("media-playback-start"))
                self.action_btn.setText(" Start")

    def _build_ui(self):
        """ساخت UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # === Title ===
        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(get_icon("video-display").pixmap(24, 24))
        title_layout.addWidget(title_icon)

        video_title = "Downloading from YouTube"
        if self.video_info:
            video_title = self.video_info.get("title", "Downloading from YouTube")

        self.title_label = QLabel(video_title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # === Video Information ===
        info_group = QGroupBox("Video Information")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(8)

        if self.video_info:
            title = self.video_info.get("title", "Unknown")
            self.title_info = QLabel(title)
            self.title_info.setWordWrap(True)
            self.title_info.setStyleSheet("font-weight: 500;")

            title_widget = QWidget()
            title_widget_layout = QHBoxLayout(title_widget)
            title_widget_layout.setContentsMargins(0, 0, 0, 0)
            title_icon_small = QLabel()
            title_icon_small.setPixmap(get_icon("text-x-generic").pixmap(16, 16))
            title_widget_layout.addWidget(title_icon_small)
            title_widget_layout.addWidget(self.title_info)
            info_layout.addRow("Title:", title_widget)

            uploader = self.video_info.get("uploader", "Unknown")
            uploader_widget = QWidget()
            uploader_layout = QHBoxLayout(uploader_widget)
            uploader_layout.setContentsMargins(0, 0, 0, 0)
            uploader_icon = QLabel()
            uploader_icon.setPixmap(get_icon("user").pixmap(16, 16))
            uploader_layout.addWidget(uploader_icon)
            uploader_layout.addWidget(QLabel(uploader))
            info_layout.addRow("Channel:", uploader_widget)

            duration = self.video_info.get("duration", 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_widget = QWidget()
            duration_layout = QHBoxLayout(duration_widget)
            duration_layout.setContentsMargins(0, 0, 0, 0)
            duration_icon = QLabel()
            duration_icon.setPixmap(get_icon("clock").pixmap(16, 16))
            duration_layout.addWidget(duration_icon)
            duration_layout.addWidget(QLabel(f"{minutes}:{seconds:02d}"))
            info_layout.addRow("Duration:", duration_widget)

            resolution = self.video_info.get("resolution", "Unknown")
            if resolution:
                res_widget = QWidget()
                res_layout = QHBoxLayout(res_widget)
                res_layout.setContentsMargins(0, 0, 0, 0)
                res_icon = QLabel()
                res_icon.setPixmap(get_icon("video-display").pixmap(16, 16))
                res_layout.addWidget(res_icon)
                res_layout.addWidget(QLabel(resolution))
                info_layout.addRow("Quality:", res_widget)

            format_names = {
                "mp4": "MP4 Video",
                "webm": "WebM Video",
                "mp3": "MP3 Audio",
                "m4a": "M4A Audio",
            }
            format_widget = QWidget()
            format_layout = QHBoxLayout(format_widget)
            format_layout.setContentsMargins(0, 0, 0, 0)
            format_icon = QLabel()
            format_icon.setPixmap(get_icon("package").pixmap(16, 16))
            format_layout.addWidget(format_icon)
            format_layout.addWidget(
                QLabel(format_names.get(self.format_type, self.format_type))
            )
            info_layout.addRow("Format:", format_widget)

            filesize = self.video_info.get("filesize")
            if filesize:
                size_widget = QWidget()
                size_layout = QHBoxLayout(size_widget)
                size_layout.setContentsMargins(0, 0, 0, 0)
                size_icon = QLabel()
                size_icon.setPixmap(get_icon("drive-harddisk").pixmap(16, 16))
                size_layout.addWidget(size_icon)
                size_layout.addWidget(QLabel(format_size(filesize)))
                info_layout.addRow("Size:", size_widget)

        # Show proxy info if available
        if self.proxy_url:
            proxy_widget = QWidget()
            proxy_layout = QHBoxLayout(proxy_widget)
            proxy_layout.setContentsMargins(0, 0, 0, 0)
            proxy_icon = QLabel()
            proxy_icon.setPixmap(get_icon("network").pixmap(16, 16))
            proxy_layout.addWidget(proxy_icon)
            proxy_label = QLabel(f"✅ {self.proxy_url}")
            proxy_label.setStyleSheet("color: #27ae60;")
            proxy_label.setWordWrap(True)
            proxy_layout.addWidget(proxy_label)
            info_layout.addRow("Proxy:", proxy_widget)

        layout.addWidget(info_group)

        # === Progress ===
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Starting...")
        self.status_label.setStyleSheet("color: #95a5a6;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.speed_eta_label = QLabel("")
        self.speed_eta_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        layout.addWidget(self.speed_eta_label)

        # === Buttons ===
        btn_layout = QHBoxLayout()

        self.action_btn = QPushButton()
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText(" Pause")
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_layout.addWidget(self.action_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(get_icon("edit-delete"))
        self.cancel_btn.setText(" Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def _create_worker(self):
        """ساخت worker برای دانلود جدید"""
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

    # ===== متدهای به‌روزرسانی از خارج =====
    def update_progress(self, progress: int, speed: str = "", eta: str = ""):
        """به‌روزرسانی پیشرفت از خارج"""
        self._progress_value = progress
        self._speed_text = speed
        self._eta_text = eta

        self.progress_bar.setValue(progress)
        self.progress_bar.setFormat(f"{progress}%")

        if speed and eta:
            self.speed_eta_label.setText(f"Speed: {speed}  |  ETA: {eta}")
        elif speed:
            self.speed_eta_label.setText(f"Speed: {speed}")
        elif eta:
            self.speed_eta_label.setText(f"ETA: {eta}")

    def update_status(self, status: str):
        """به‌روزرسانی وضعیت از خارج"""
        self._status_text = status
        self.status_label.setText(status)

        # تغییر رنگ بر اساس وضعیت
        if "Downloading" in status or "⬇" in status:
            self.status_label.setStyleSheet("color: #3daee9;")
        elif "Paused" in status or "⏸" in status:
            self.status_label.setStyleSheet("color: #f39c12;")
        elif "Complete" in status or "✅" in status:
            self.status_label.setStyleSheet("color: #27ae60;")
        elif "Error" in status or "❌" in status:
            self.status_label.setStyleSheet("color: #e74c3c;")

    def update_finished(self, success: bool, message: str):
        """به‌روزرسانی پایان دانلود از خارج"""
        print(
            f"📢 [Dialog] update_finished called: success={success}, message={message}"
        )

        if success:
            self._is_complete = True
            self.title_label.setText("✅ Download completed!")
            self.title_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #27ae60;"
            )
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #27ae60;")
            self.speed_eta_label.setText("")
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat("100%")

            # ===== تغییر دکمه به Open Folder =====
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText(" Open Folder")
            self.action_btn.setEnabled(True)
            try:
                self.action_btn.clicked.disconnect()
            except:
                pass
            self.action_btn.clicked.connect(self._open_folder)

            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            try:
                self.cancel_btn.clicked.disconnect()
            except:
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
            self.title_label.setText("❌ Download failed!")
            self.title_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #e74c3c;"
            )
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.action_btn.setEnabled(False)
            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            try:
                self.cancel_btn.clicked.disconnect()
            except:
                pass
            self.cancel_btn.clicked.connect(self.reject)

    def get_worker(self):
        """دریافت worker (برای اتصال سیگنال از خارج)"""
        return self._worker

    # ===== سیگنال‌های داخلی =====
    def _on_progress(self, value):
        self._progress_value = value
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"{value}%")

    def _on_status(self, text):
        self._status_text = text
        self.status_label.setText(text)
        if "Downloading" in text or "⬇" in text:
            self.status_label.setStyleSheet("color: #3daee9;")

    def _on_speed_eta(self, speed, eta):
        self._speed_text = speed
        self._eta_text = eta
        if speed and eta:
            self.speed_eta_label.setText(f"Speed: {speed}  |  ETA: {eta}")
        elif speed:
            self.speed_eta_label.setText(f"Speed: {speed}")
        elif eta:
            self.speed_eta_label.setText(f"ETA: {eta}")
        else:
            self.speed_eta_label.setText("")

    def _on_paused(self):
        """Handle pause"""
        self._is_paused = True
        self.action_btn.setIcon(get_icon("media-playback-start"))
        self.action_btn.setText(" Resume")
        self.status_label.setText("⏸ Paused")
        self.status_label.setStyleSheet("color: #f39c12;")
        print(f"⏸️ [Dialog] Paused state updated")

    def _on_resumed(self):
        """Handle resume"""
        self._is_paused = False
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText(" Pause")
        self.status_label.setText("▶ Downloading...")
        self.status_label.setStyleSheet("color: #3daee9;")
        print(f"▶️ [Dialog] Resumed state updated")

    def update_pause_state(self, is_paused: bool):
        """به‌روزرسانی وضعیت Pause از خارج"""
        print(f"🔄 [Dialog] update_pause_state called: is_paused={is_paused}")
        if is_paused:
            self._on_paused()
        else:
            self._on_resumed()

    def _on_action_clicked(self):
        """دکمه اکشن (Pause/Resume/Open Folder)"""
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
                else:
                    print(f"⚠️ [Dialog] No parent or _current_queue available")

                print(f"▶️ [Dialog] Emitting resume_requested for {self.download_id}")
                self.resume_requested.emit(self.download_id)

            elif current_text == "Pause":
                print(f"⏸️ [Dialog] Emitting pause_requested for {self.download_id}")
                self.pause_requested.emit(self.download_id)
            return

        if self._worker:
            current_text = self.action_btn.text().strip()
            if current_text == "Pause":
                self._worker.pause()
            else:
                self._worker.resume()

    def _on_cancel_clicked(self):
        """دکمه Cancel/Close"""
        if self._is_complete:
            self.accept()
            return

        # ===== اگر دانلود موجود هست، سیگنال بفرست =====
        if self._is_existing_download and self.download_id:
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Are you sure you want to cancel this download?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.cancel_requested.emit(self.download_id)
                self.status_label.setText("⏹ Cancelled")
                self.status_label.setStyleSheet("color: #f39c12;")
                self.action_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)
                QTimer.singleShot(500, self.reject)
            return

        # ===== اگر worker داریم =====
        if self._worker:
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Are you sure you want to cancel this download?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self.status_label.setText("⏹ Cancelled")
                self.status_label.setStyleSheet("color: #f39c12;")
                self.action_btn.setEnabled(False)
                self.cancel_btn.setEnabled(False)
                QTimer.singleShot(500, self.reject)

    def _on_finished(self, success, message):
        """پایان دانلود"""
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self._is_complete = True
            self.title_label.setText("✅ Download completed!")
            self.title_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #27ae60;"
            )
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #27ae60;")
            self.speed_eta_label.setText("")

            # ===== تغییر دکمه به Open Folder =====
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText(" Open Folder")
            self.action_btn.setEnabled(True)
            self.action_btn.clicked.disconnect()
            self.action_btn.clicked.connect(self._open_folder)

            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            self.cancel_btn.clicked.disconnect()
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
            self.title_label.setText("❌ Download failed!")
            self.title_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #e74c3c;"
            )
            self.status_label.setText(message)
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.action_btn.setEnabled(False)
            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            self.cancel_btn.clicked.disconnect()
            self.cancel_btn.clicked.connect(self.reject)

    def set_action_button_enabled(self, enabled: bool):
        """فعال/غیرفعال کردن دکمه اکشن"""
        self.action_btn.setEnabled(enabled)

    def _open_folder(self):
        """باز کردن پوشه"""
        if self._file_path and os.path.exists(self._file_path):
            folder = os.path.dirname(self._file_path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            if os.path.exists(self.output_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_path))
            else:
                QMessageBox.warning(self, "Folder Not Found", "Folder not found.")

    def closeEvent(self, event):
        """بستن دیالوگ"""
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
