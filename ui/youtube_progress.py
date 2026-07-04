# ui/youtube_progress.py

import os
from PyQt6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout, QGroupBox, QFormLayout, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from core.youtube_worker import YouTubeWorker
from utils.helpers import format_size, get_icon

class YouTubeProgressDialog(QDialog):
    def __init__(self, url, output_path, format_type="mp4", cookie_file=None, video_info=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        title_layout = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(get_icon('video-display').pixmap(24, 24))
        title_layout.addWidget(title_icon)
        
        video_title = "Downloading from YouTube"
        if video_info:
            video_title = video_info.get("title", "Downloading from YouTube")
        
        self.title_label = QLabel(video_title)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        layout.addLayout(title_layout)
        
        info_group = QGroupBox("Video Information")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(8)
        
        if video_info:
            title = video_info.get("title", "Unknown")
            self.title_info = QLabel(title)
            self.title_info.setWordWrap(True)
            self.title_info.setStyleSheet("font-weight: 500;")
            
            title_widget = QWidget()
            title_widget_layout = QHBoxLayout(title_widget)
            title_widget_layout.setContentsMargins(0, 0, 0, 0)
            title_icon_small = QLabel()
            title_icon_small.setPixmap(get_icon('text-x-generic').pixmap(16, 16))
            title_widget_layout.addWidget(title_icon_small)
            title_widget_layout.addWidget(self.title_info)
            info_layout.addRow("Title:", title_widget)
            
            uploader = video_info.get("uploader", "Unknown")
            uploader_widget = QWidget()
            uploader_layout = QHBoxLayout(uploader_widget)
            uploader_layout.setContentsMargins(0, 0, 0, 0)
            uploader_icon = QLabel()
            uploader_icon.setPixmap(get_icon('user').pixmap(16, 16))
            uploader_layout.addWidget(uploader_icon)
            uploader_layout.addWidget(QLabel(uploader))
            info_layout.addRow("Channel:", uploader_widget)
            
            duration = video_info.get("duration", 0)
            minutes = duration // 60
            seconds = duration % 60
            duration_widget = QWidget()
            duration_layout = QHBoxLayout(duration_widget)
            duration_layout.setContentsMargins(0, 0, 0, 0)
            duration_icon = QLabel()
            duration_icon.setPixmap(get_icon('clock').pixmap(16, 16))
            duration_layout.addWidget(duration_icon)
            duration_layout.addWidget(QLabel(f"{minutes}:{seconds:02d}"))
            info_layout.addRow("Duration:", duration_widget)
            
            resolution = video_info.get("resolution", "Unknown")
            if resolution:
                res_widget = QWidget()
                res_layout = QHBoxLayout(res_widget)
                res_layout.setContentsMargins(0, 0, 0, 0)
                res_icon = QLabel()
                res_icon.setPixmap(get_icon('video-display').pixmap(16, 16))
                res_layout.addWidget(res_icon)
                res_layout.addWidget(QLabel(resolution))
                info_layout.addRow("Quality:", res_widget)
            
            format_names = {
                "mp4": "MP4 Video",
                "webm": "WebM Video",
                "mp3": "MP3 Audio",
                "m4a": "M4A Audio"
            }
            format_widget = QWidget()
            format_layout = QHBoxLayout(format_widget)
            format_layout.setContentsMargins(0, 0, 0, 0)
            format_icon = QLabel()
            format_icon.setPixmap(get_icon('package').pixmap(16, 16))
            format_layout.addWidget(format_icon)
            format_layout.addWidget(QLabel(format_names.get(format_type, format_type)))
            info_layout.addRow("Format:", format_widget)
            
            filesize = video_info.get("filesize")
            if filesize:
                size_widget = QWidget()
                size_layout = QHBoxLayout(size_widget)
                size_layout.setContentsMargins(0, 0, 0, 0)
                size_icon = QLabel()
                size_icon.setPixmap(get_icon('drive-harddisk').pixmap(16, 16))
                size_layout.addWidget(size_icon)
                size_layout.addWidget(QLabel(format_size(filesize)))
                info_layout.addRow("Size:", size_widget)
        
        layout.addWidget(info_group)
        
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
        
        btn_layout = QHBoxLayout()
        
        self.pause_btn = QPushButton()
        self.pause_btn.setIcon(get_icon('media-playback-pause'))
        self.pause_btn.setText(" Pause")
        self.pause_btn.clicked.connect(self._on_pause)
        btn_layout.addWidget(self.pause_btn)
        
        self.resume_btn = QPushButton()
        self.resume_btn.setIcon(get_icon('media-playback-start'))
        self.resume_btn.setText(" Resume")
        self.resume_btn.clicked.connect(self._on_resume)
        self.resume_btn.setEnabled(False)
        btn_layout.addWidget(self.resume_btn)
        
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(get_icon('edit-delete'))
        self.cancel_btn.setText(" Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(btn_layout)
        
        self.worker = YouTubeWorker(url, output_path, format_type, cookie_file)
        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self._on_status)
        self.worker.speed_eta.connect(self._on_speed_eta)
        self.worker.finished.connect(self._on_finished)
        self.worker.paused.connect(self._on_paused)
        self.worker.resumed.connect(self._on_resumed)
        self.worker.start()
    
    def _on_progress(self, value):
        self.progress_bar.setValue(value)
        self.progress_bar.setFormat(f"{value}%")
    
    def _on_status(self, text):
        self.status_label.setText(text)
    
    def _on_speed_eta(self, speed, eta):
        self.speed_eta_label.setText(f"Speed: {speed}  |  ETA: {eta}")
    
    def _on_paused(self):
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(True)
        self.status_label.setText("Paused")
    
    def _on_resumed(self):
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)
        self.status_label.setText("Resuming...")
    
    def _on_pause(self):
        if hasattr(self, 'worker'):
            self.worker.pause()
    
    def _on_resume(self):
        if hasattr(self, 'worker'):
            self.worker.resume()
    
    def _on_finished(self, success, message):
        self.progress_bar.setValue(100 if success else 0)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        
        if success:
            self.title_label.setText("✅ Download completed!")
            self.status_label.setText(message)
            self.speed_eta_label.setText("")
            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon('window-close'))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.disconnect()
            self.cancel_btn.clicked.connect(self.accept)
        else:
            self.title_label.setText("❌ Download failed!")
            self.status_label.setText(message)
            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon('window-close'))
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.clicked.disconnect()
            self.cancel_btn.clicked.connect(self.reject)
    
    def _on_cancel(self):
        if hasattr(self, 'worker'):
            self.worker.cancel()
        self.reject()
    
    def closeEvent(self, event):
        """When user closes the dialog"""
        if hasattr(self, 'worker') and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Cancel Download",
                "Download is in progress. Are you sure you want to cancel?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Cancel and wait for thread to finish
                self.worker.cancel()
                self.worker.wait() 
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
            
