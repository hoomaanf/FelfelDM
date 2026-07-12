# ui/dialogs.py

import os
from PyQt6.QtWidgets import *
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import *
from utils.helpers import get_icon
from core.queue_model import Queue
from datetime import datetime, time as dtime
from core.proxy_manager import ProxyType, ProxyConfig


class AddDownloadDialog(QDialog):
    def __init__(self, queues, default_queue=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Downloads")
        self.setMinimumWidth(580)
        self.setMinimumHeight(450)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        # === URL Group ===
        url_group = QGroupBox("URLs")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        url_layout.addWidget(self.url_edit)

        import_btn = QPushButton(get_icon("document-open"), "Import from File")
        import_btn.clicked.connect(self._import_from_txt)
        url_layout.addWidget(import_btn)
        lay.addWidget(url_group)

        # === Save Location Group ===
        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon("folder-open"), "Browse...")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        # === Options Group ===
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self.queue_cb = QComboBox()
        for q in queues:
            if q.name != "__direct__":
                self.queue_cb.addItem(q.name)
        self.queue_cb.setCurrentIndex(default_queue)
        options_layout.addRow("Queue:", self.queue_cb)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        options_layout.addRow("Connections:", self.conn_spin)
        lay.addWidget(options_group)

        # === Proxy Settings Group ===
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            [
                "Use Global/Queue Proxy",
                "Custom Proxy for this download",
                "No Proxy (Direct Connection)",
            ]
        )
        self.proxy_combo.setCurrentIndex(0)
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_layout.addWidget(self.proxy_combo)

        # Custom proxy config button
        proxy_btn_layout = QHBoxLayout()
        self.proxy_config_btn = QPushButton(
            get_icon("configure"), "Configure Custom Proxy"
        )
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        self.proxy_config_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), "Clear")
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        self.proxy_clear_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_clear_btn)
        proxy_btn_layout.addStretch()
        proxy_layout.addLayout(proxy_btn_layout)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 2px;"
        )
        self.proxy_status_label.setWordWrap(True)
        proxy_layout.addWidget(self.proxy_status_label)

        lay.addWidget(proxy_group)

        # === Info Label ===
        info_label = QLabel("ℹ️ Downloads will be added in Paused state")
        info_label.setStyleSheet("color: #95a5a6; font-size: 10px; padding: 4px;")
        lay.addWidget(info_label)

        # === Buttons ===
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        # Custom proxy storage
        self._custom_proxy = None

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Links File", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    current_text = self.url_edit.toPlainText().strip()
                    combined = (
                        current_text + "\n" + "\n".join(lines)
                        if current_text
                        else "\n".join(lines)
                    )
                    self.url_edit.setPlainText(combined)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse file:\n{str(e)}")

    def _on_proxy_mode_changed(self, index):
        """Enable/disable custom proxy config based on selection"""
        is_custom = index == 1  # Custom proxy mode
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)

        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        """Open custom proxy configuration dialog"""
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
        """Clear custom proxy"""
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")
        self.proxy_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")

    def _update_proxy_status(self):
        """Update status label with custom proxy info"""
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✅ Custom: {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        else:
            self.proxy_status_label.setText("⚠️ Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def _get_urls(self):
        """Get list of URLs from text edit"""
        raw_text = self.url_edit.toPlainText()
        return [line.strip() for line in raw_text.split("\n") if line.strip()]

    def get_data(self):
        """Get all dialog data"""
        urls = self._get_urls()
        proxy_mode = self.proxy_combo.currentIndex()  # 0: global, 1: custom, 2: none

        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "queue": self.queue_cb.currentIndex(),
            "connections": self.conn_spin.value(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }


class SingleDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Single Download")
        self.setMinimumWidth(500)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # === URL Group ===
        url_group = QGroupBox("URL")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        url_layout.addWidget(self.url_edit)
        lay.addWidget(url_group)

        # === Save Location Group ===
        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon("folder-open"), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        # === Options Group ===
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        options_layout.addRow("Connections:", self.conn_spin)

        self.start_immediately = QCheckBox("Start download immediately")
        self.start_immediately.setChecked(True)
        options_layout.addRow("", self.start_immediately)

        lay.addWidget(options_group)

        # === Proxy Settings Group ===
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            [
                "Use Global/Queue Proxy",
                "Custom Proxy for this download",
                "No Proxy (Direct Connection)",
            ]
        )
        self.proxy_combo.setCurrentIndex(0)
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_layout.addWidget(self.proxy_combo)

        # Custom proxy config button
        proxy_btn_layout = QHBoxLayout()
        self.proxy_config_btn = QPushButton(
            get_icon("configure"), "Configure Custom Proxy"
        )
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        self.proxy_config_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), "Clear")
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        self.proxy_clear_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_clear_btn)
        proxy_btn_layout.addStretch()
        proxy_layout.addLayout(proxy_btn_layout)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 2px;"
        )
        self.proxy_status_label.setWordWrap(True)
        proxy_layout.addWidget(self.proxy_status_label)

        lay.addWidget(proxy_group)

        # === Buttons ===
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        # Custom proxy storage
        self._custom_proxy = None

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _on_proxy_mode_changed(self, index):
        """Enable/disable custom proxy config based on selection"""
        is_custom = index == 1  # Custom proxy mode
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)

        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        """Open custom proxy configuration dialog"""
        from ui.download_proxy_dialog import DownloadProxyDialog

        # Get URL for display name
        url = self.url_edit.text().strip()
        display_name = os.path.basename(url) if url else "Single Download"

        dlg = DownloadProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            data = dlg.get_data()
            if data["use_custom"] and data["config"]:
                self._custom_proxy = data["config"]
                self.proxy_clear_btn.setEnabled(True)
                self._update_proxy_status()
            else:
                self._custom_proxy = None
                self.proxy_clear_btn.setEnabled(False)
                self.proxy_status_label.setText("")

    def _clear_custom_proxy(self):
        """Clear custom proxy"""
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")
        self.proxy_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")

    def _update_proxy_status(self):
        """Update status label with custom proxy info"""
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✅ Custom: {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        else:
            self.proxy_status_label.setText("⚠️ Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def get_data(self):
        """Get all dialog data"""
        proxy_mode = self.proxy_combo.currentIndex()  # 0: global, 1: custom, 2: none

        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }


class QueueSettingsDialog(QDialog):
    def __init__(self, queue: Queue, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Queue Settings — {queue.name}")
        self.setMinimumWidth(480)

        lay = QFormLayout(self)

        self.name_edit = QLineEdit(queue.name)
        lay.addRow("Queue Name:", self.name_edit)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(queue.save_path)
        path_row.addWidget(self.path_edit)
        browse = QPushButton(get_icon("folder-open"), "Browse...")
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        lay.addRow("Default Directory:", path_row)

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 20)
        self.conc_spin.setValue(queue.max_concurrent)
        lay.addRow("Max Concurrent:", self.conc_spin)

        self.sched_cb = QCheckBox("Enable Schedule")
        self.sched_cb.setChecked(queue.schedule_enabled)
        lay.addRow(self.sched_cb)

        time_row = QHBoxLayout()
        self.start_time = QTimeEdit(
            QTime(queue.schedule_start.hour, queue.schedule_start.minute)
        )
        self.end_time = QTimeEdit(
            QTime(queue.schedule_end.hour, queue.schedule_end.minute)
        )
        time_row.addWidget(QLabel("From:"))
        time_row.addWidget(self.start_time)
        time_row.addWidget(QLabel("To:"))
        time_row.addWidget(self.end_time)
        self.start_time.setDisplayFormat("HH:mm")
        self.end_time.setDisplayFormat("HH:mm")
        lay.addRow("Time Window:", time_row)

        days_row = QHBoxLayout()
        self.day_checks = []
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            cb = QCheckBox(d)
            cb.setChecked(i in queue.days)
            self.day_checks.append(cb)
            days_row.addWidget(cb)
        lay.addRow("Active Days:", days_row)

        speed_group = QGroupBox("Speed Limit")
        speed_layout = QVBoxLayout(speed_group)

        speed_limit_row = QHBoxLayout()
        self.queue_speed_enabled = QCheckBox("Enable Speed Limit")
        self.queue_speed_enabled.setChecked(getattr(queue, "speed_limit", 0) > 0)
        self.queue_speed_enabled.toggled.connect(self._toggle_queue_speed)

        self.queue_speed_spin = QSpinBox()
        self.queue_speed_spin.setRange(0, 999999)
        self.queue_speed_spin.setSuffix(" KB/s")
        self.queue_speed_spin.setValue(getattr(queue, "speed_limit", 0) or 1024)
        self.queue_speed_spin.setEnabled(self.queue_speed_enabled.isChecked())
        self.queue_speed_spin.setMinimumWidth(120)

        speed_limit_row.addWidget(self.queue_speed_enabled)
        speed_limit_row.addWidget(self.queue_speed_spin)
        speed_limit_row.addStretch()
        speed_layout.addLayout(speed_limit_row)

        speed_info = QLabel("💡 0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 10px;")
        speed_layout.addWidget(speed_info)

        lay.addRow(speed_group)

        # Proxy Settings for Queue
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)

        self.queue_proxy_cb = QCheckBox("Use custom proxy for this queue")
        self.queue_proxy_cb.setChecked(False)
        self.queue_proxy_cb.toggled.connect(self._toggle_queue_proxy)
        proxy_layout.addWidget(self.queue_proxy_cb)

        proxy_config_layout = QHBoxLayout()
        self.queue_proxy_status = QLabel("Using global proxy")
        self.queue_proxy_status.setStyleSheet("color: #95a5a6; font-size: 10px;")
        proxy_config_layout.addWidget(self.queue_proxy_status)
        proxy_config_layout.addStretch()

        self.queue_proxy_btn = QPushButton("Configure Queue Proxy")
        self.queue_proxy_btn.clicked.connect(self._configure_queue_proxy)
        self.queue_proxy_btn.setEnabled(False)
        proxy_config_layout.addWidget(self.queue_proxy_btn)

        proxy_layout.addLayout(proxy_config_layout)
        lay.addRow(proxy_group)

        # Load existing proxy config if any
        self._queue_proxy_config = None
        self._load_queue_proxy()

        if queue.proxy_config:
            self._queue_proxy_config = queue.proxy_config
            self.queue_proxy_cb.setChecked(True)
            self.queue_proxy_status.setText(
                f"✅ {queue.proxy_config.get_display_string()}"
            )
            self.queue_proxy_status.setStyleSheet("color: #27ae60; font-size: 10px;")
            self.queue_proxy_btn.setEnabled(True)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addRow(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def get_queue_data(self):
        """Get queue settings data from dialog"""
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

    def _load_queue_proxy(self):
        """Load proxy config for this queue"""
        from core.proxy_manager import ProxyManager

        if hasattr(self.parent(), "store"):
            proxy_mgr = ProxyManager(self.parent().store)
            queue_proxy = proxy_mgr.get_queue_proxy(self.name_edit.text())

            if queue_proxy and queue_proxy.host:
                self.queue_proxy_cb.setChecked(True)
                self.queue_proxy_status.setText(
                    f"✅ {queue_proxy.get_display_string()}"
                )
                self.queue_proxy_status.setStyleSheet(
                    "color: #27ae60; font-size: 10px;"
                )
                self.queue_proxy_btn.setEnabled(True)
                self._queue_proxy_config = queue_proxy
            else:
                self.queue_proxy_cb.setChecked(False)
                self.queue_proxy_status.setText("Using global proxy")
                self.queue_proxy_status.setStyleSheet(
                    "color: #95a5a6; font-size: 10px;"
                )
                self.queue_proxy_btn.setEnabled(False)
                self._queue_proxy_config = None

    def _toggle_queue_proxy(self, checked):
        self.queue_proxy_btn.setEnabled(checked)
        if checked:
            self.queue_proxy_status.setText("Click 'Configure' to set proxy")
            self.queue_proxy_status.setStyleSheet("color: #f39c12; font-size: 10px;")
        else:
            self.queue_proxy_status.setText("Using global proxy")
            self.queue_proxy_status.setStyleSheet("color: #95a5a6; font-size: 10px;")
            self._queue_proxy_config = None

    def _configure_queue_proxy(self):
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyConfig

        current = getattr(self, "_queue_proxy_config", None) or ProxyConfig()
        dlg = ProxyDialog(current, self, f"Queue Proxy: {self.name_edit.text()}")

        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._queue_proxy_config = new_config
            self.queue_proxy_status.setText(f"✅ {new_config.get_display_string()}")
            self.queue_proxy_status.setStyleSheet("color: #27ae60; font-size: 10px;")

    def _toggle_queue_speed(self, checked):
        self.queue_speed_spin.setEnabled(checked)


class QuickDownloadDialog(QDialog):
    def __init__(self, queues, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Download")
        self.setMinimumWidth(520)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # === URL Group ===
        url_group = QGroupBox("URLs")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        url_layout.addWidget(self.url_edit)
        lay.addWidget(url_group)

        # === Save Location Group ===
        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon("folder-open"), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        # === Queue Selection ===
        queue_group = QGroupBox("Add to Queue")
        queue_layout = QVBoxLayout(queue_group)
        self.queue_combo = QComboBox()

        # Populate queues from parameter
        self.queue_combo.addItem("Direct Downloads (Quick)", "__direct__")
        for q in queues:
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, q.name)

        queue_layout.addWidget(self.queue_combo)
        lay.addWidget(queue_group)

        # === Options Group ===
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        options_layout.addRow("Connections:", self.conn_spin)

        # Start Immediately Checkbox
        self.start_immediately = QCheckBox("Start download immediately")
        self.start_immediately.setChecked(True)
        options_layout.addRow("", self.start_immediately)

        lay.addWidget(options_group)

        # === Proxy Settings Group ===
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            [
                "Use Global Proxy",
                "Custom Proxy for this download",
                "No Proxy (Direct Connection)",
            ]
        )
        self.proxy_combo.setCurrentIndex(0)
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_layout.addWidget(self.proxy_combo)

        # Custom proxy config button
        proxy_btn_layout = QHBoxLayout()
        self.proxy_config_btn = QPushButton(
            get_icon("configure"), "Configure Custom Proxy"
        )
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        self.proxy_config_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), "Clear")
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        self.proxy_clear_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_clear_btn)
        proxy_btn_layout.addStretch()
        proxy_layout.addLayout(proxy_btn_layout)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 2px;"
        )
        self.proxy_status_label.setWordWrap(True)
        proxy_layout.addWidget(self.proxy_status_label)

        lay.addWidget(proxy_group)

        # === Buttons ===
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        self._custom_proxy = None

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)

        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import DownloadProxyDialog

        urls = self._get_urls()
        display_name = os.path.basename(urls[0]) if urls else "Quick Download"

        dlg = DownloadProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            data = dlg.get_data()
            if data["use_custom"] and data["config"]:
                self._custom_proxy = data["config"]
                self.proxy_clear_btn.setEnabled(True)
                self._update_proxy_status()
            else:
                self._custom_proxy = None
                self.proxy_clear_btn.setEnabled(False)
                self.proxy_status_label.setText("")

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")
        self.proxy_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✅ Custom: {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        else:
            self.proxy_status_label.setText("⚠️ Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def _get_urls(self):
        raw_text = self.url_edit.toPlainText()
        return [line.strip() for line in raw_text.split("\n") if line.strip()]

    def get_data(self):
        raw = self.url_edit.toPlainText()
        urls = [l.strip() for l in raw.split("\n") if l.strip()]
        proxy_mode = self.proxy_combo.currentIndex()

        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "queue_name": self.queue_combo.currentData(),
            "start_immediately": self.start_immediately.isChecked(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }


class DownloadProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)
    cancel_with_delete_requested = pyqtSignal(str)

    def __init__(self, gid, dl_data, parent=None):
        super().__init__(parent)
        self.gid = gid
        self.setWindowTitle("Download Progress")
        self.setMinimumWidth(480)
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

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.name_lbl = QLabel(dl_data.get("name", "Unknown"))
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        lay.addWidget(self.name_lbl)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        lay.addWidget(self.progress_bar)

        # Info Group
        info_group = QGroupBox("Info")
        info_lay = QFormLayout(info_group)
        self.size_lbl = QLabel("—")
        self.speed_lbl = QLabel("—")
        self.eta_lbl = QLabel("—")
        self.conn_lbl = QLabel("—")
        self.status_lbl = QLabel("—")
        info_lay.addRow("Size:", self.size_lbl)
        info_lay.addRow("Speed:", self.speed_lbl)
        info_lay.addRow("ETA:", self.eta_lbl)
        info_lay.addRow("Connections:", self.conn_lbl)
        info_lay.addRow("Status:", self.status_lbl)
        lay.addWidget(info_group)

        btn_lay = QHBoxLayout()

        self.action_btn = QPushButton()
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText(" Pause")
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_lay.addWidget(self.action_btn)

        btn_lay.addStretch()

        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(get_icon("edit-delete"))
        self.cancel_btn.setText(" Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_lay.addWidget(self.cancel_btn)

        lay.addLayout(btn_lay)

        self._status = "unknown"
        self._is_complete = False
        self._file_path = None

        if dl_data:
            files = dl_data.get("files", [])
            if files and files[0].get("path"):
                self._file_path = files[0]["path"]

        self.update_data(dl_data)

    def _on_action_clicked(self):
        """Handle action button click (Pause/Resume/Open)"""
        if self._is_complete:
            if self._file_path and os.path.exists(self._file_path):
                folder = os.path.dirname(self._file_path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            else:
                QMessageBox.warning(self, "Folder Not Found", "Folder not found.")
            return

        # Pause/Resume
        if self._status == "active":
            self.pause_requested.emit(self.gid)
        elif self._status in ["paused", "waiting"]:
            self.resume_requested.emit(self.gid)

    def _on_cancel_clicked(self):
        """Handle cancel button click"""
        if self._is_complete:
            self.close()
            return

        reply = QMessageBox.question(
            self,
            "Cancel Download",
            "Are you sure you want to cancel this download?\n\n"
            "Do you also want to delete the downloaded files?",
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
        """Update dialog with new data"""
        from utils.helpers import format_size, format_speed

        if not dl_data:
            return

        total = int(dl_data.get("totalLength", 0))
        completed = int(dl_data.get("completedLength", 0))
        speed = int(dl_data.get("downloadSpeed", 0))
        status = dl_data.get("status", "unknown")
        name = dl_data.get("name", "")

        self._status = status
        self._is_complete = status == "complete"

        files = dl_data.get("files", [])
        if files and files[0].get("path"):
            self._file_path = files[0]["path"]

        if name:
            self.name_lbl.setText(name)

        # Progress bar
        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(min(pct, 100))
            self.progress_bar.setFormat(f"{pct}%")
            self.size_lbl.setText(f"{format_size(completed)} / {format_size(total)}")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("—")
            self.size_lbl.setText(f"{format_size(completed)} / Unknown")

        # Speed & ETA
        if status == "paused":
            self.speed_lbl.setText("0 B/s")
            self.eta_lbl.setText("—")
        else:
            self.speed_lbl.setText(format_speed(speed) if speed > 0 else "—")
            if speed > 0 and total > completed:
                eta_sec = (total - completed) // speed
                h, m, s = eta_sec // 3600, (eta_sec % 3600) // 60, eta_sec % 60
                self.eta_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
            else:
                self.eta_lbl.setText("—")

        self.conn_lbl.setText(str(dl_data.get("connections", 0)))

        status_map = {
            "active": "⬇ Downloading",
            "waiting": "⏳ Waiting",
            "paused": "⏸ Paused",
            "complete": "✅ Complete",
            "error": "❌ Error",
            "removed": "🗑 Removed",
        }
        self.status_lbl.setText(status_map.get(status, status.capitalize()))

        status_colors = {
            "active": "#3daee9",
            "waiting": "#95a5a6",
            "paused": "#f39c12",
            "complete": "#27ae60",
            "error": "#e74c3c",
        }
        self.status_lbl.setStyleSheet(
            f"color: {status_colors.get(status, '#95a5a6')}; font-weight: bold;"
        )

        self._update_buttons(status)

    def _update_buttons(self, status):
        """Update button states based on download status"""

        if status == "complete":
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText(" Open Folder")
            self.action_btn.setEnabled(True)

            self.cancel_btn.setText(" Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            self.cancel_btn.setEnabled(True)

        elif status == "active":
            self.action_btn.setIcon(get_icon("media-playback-pause"))
            self.action_btn.setText(" Pause")
            self.action_btn.setEnabled(True)

            self.cancel_btn.setText(" Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)

        elif status == "paused":
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText(" Resume")
            self.action_btn.setEnabled(True)

            self.cancel_btn.setText(" Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)

        elif status == "waiting":
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText(" Start")
            self.action_btn.setEnabled(True)

            self.cancel_btn.setText(" Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)

        else:
            self.action_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
        self.settings = settings

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # === aria2 RPC ===
        rpc_group = QGroupBox("aria2 RPC")
        rpc_layout = QFormLayout(rpc_group)
        self.host = QLineEdit(settings.get("aria2_host", "http://localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.get("aria2_port", 6800))
        self.secret = QLineEdit(settings.get("aria2_secret", ""))
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        rpc_layout.addRow("Host:", self.host)
        rpc_layout.addRow("Port:", self.port)
        rpc_layout.addRow("Secret:", self.secret)
        lay.addWidget(rpc_group)

        # === Download Settings ===
        dl_group = QGroupBox("Download")
        dl_layout = QFormLayout(dl_group)
        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 50)
        self.max_concurrent.setValue(settings.get("max_concurrent", 5))
        self.max_tries = QSpinBox()
        self.max_tries.setRange(0, 100)
        self.max_tries.setSpecialValueText("Unlimited")
        self.max_tries.setValue(settings.get("max_tries", 0))
        self.conns = QSpinBox()
        self.conns.setRange(1, 16)
        self.conns.setValue(settings.get("connections", 8))
        dl_layout.addRow("Max Concurrent Downloads:", self.max_concurrent)
        dl_layout.addRow("Max Retry Attempts:", self.max_tries)
        dl_layout.addRow("Default Connections:", self.conns)
        lay.addWidget(dl_group)

        # === Theme ===
        theme_group = QGroupBox("Appearance")
        theme_layout = QFormLayout(theme_group)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Dark", "Light"])
        current_theme = settings.get("theme", "auto").capitalize()
        index = self.theme_combo.findText(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        theme_layout.addRow("Theme:", self.theme_combo)
        lay.addWidget(theme_group)

        # === Global Speed Limit ===
        speed_group = QGroupBox("Global Speed Limit")
        speed_layout = QVBoxLayout(speed_group)

        speed_limit_row = QHBoxLayout()
        self.global_speed_enabled = QCheckBox("Enable Global Speed Limit")
        self.global_speed_enabled.setChecked(settings.get("speed_limit", 0) > 0)
        self.global_speed_enabled.toggled.connect(self._toggle_global_speed)

        self.global_speed_spin = QSpinBox()
        self.global_speed_spin.setRange(0, 999999)
        self.global_speed_spin.setSuffix(" KB/s")
        self.global_speed_spin.setValue(settings.get("speed_limit", 1024))
        self.global_speed_spin.setEnabled(self.global_speed_enabled.isChecked())
        self.global_speed_spin.setMinimumWidth(120)

        speed_limit_row.addWidget(self.global_speed_enabled)
        speed_limit_row.addWidget(self.global_speed_spin)
        speed_limit_row.addStretch()
        speed_layout.addLayout(speed_limit_row)

        speed_info = QLabel("💡 0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 10px;")
        speed_layout.addWidget(speed_info)

        lay.addWidget(speed_group)

        # === Proxy Settings ===
        proxy_group = QGroupBox("Proxy")
        proxy_layout = QVBoxLayout(proxy_group)

        proxy_status_layout = QHBoxLayout()
        self.proxy_status_label = QLabel("⛔ Disabled")
        self.proxy_status_label.setStyleSheet("color: #95a5a6;")
        proxy_status_layout.addWidget(self.proxy_status_label)
        proxy_status_layout.addStretch()

        self.proxy_edit_btn = QPushButton(get_icon("configure"), "Configure Proxy")
        self.proxy_edit_btn.clicked.connect(self._configure_global_proxy)
        proxy_status_layout.addWidget(self.proxy_edit_btn)

        proxy_layout.addLayout(proxy_status_layout)

        # Proxy info
        self.proxy_info_label = QLabel("")
        self.proxy_info_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        proxy_layout.addWidget(self.proxy_info_label)

        lay.addWidget(proxy_group)

        # Update proxy status
        self._update_proxy_status()

        # === Cleanup ===
        cleanup_group = QGroupBox("Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        self.auto_clear_completed = QCheckBox("Auto-clear completed downloads")
        self.auto_clear_completed.setChecked(
            settings.get("auto_clear_completed", False)
        )
        cleanup_layout.addWidget(self.auto_clear_completed)
        lay.addWidget(cleanup_group)

        # === Service ===
        service_group = QGroupBox("Service")
        service_layout = QVBoxLayout(service_group)

        self.run_as_service = QCheckBox(
            "Run as background service (auto-start on login)"
        )
        self.run_as_service.setChecked(settings.get("run_as_service", False))
        self.run_as_service.toggled.connect(self._on_service_toggle)
        service_layout.addWidget(self.run_as_service)

        self.service_status = QLabel("")
        self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        service_layout.addWidget(self.service_status)

        lay.addWidget(service_group)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        # Update status on load
        self._update_service_status()

    def _update_service_status(self):
        """Update service status label"""
        if self.run_as_service.isChecked():
            self.service_status.setText("✅ Service is active")
            self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.service_status.setText("🔹 Service is inactive")
            self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")

    def _on_service_toggle(self, checked):
        if checked:
            self.service_status.setText("⏳ Installing service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            self.run_as_service.setEnabled(False)
            QApplication.processEvents()

            QTimer.singleShot(100, self._install_service_async)
        else:
            self.service_status.setText("⏳ Removing service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            self.run_as_service.setEnabled(False)
            QApplication.processEvents()

            QTimer.singleShot(100, self._remove_service_async)

    def _install_service_async(self):
        try:
            import subprocess
            import os
            import time

            import sys

            if getattr(sys, "frozen", False):
                exe_path = sys.executable
            else:
                exe_path = "/usr/local/bin/FelfelDM"

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

            self.service_status.setText("✅ Service installed and running")
            self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

        except Exception as e:
            self.service_status.setText(f"❌ Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

    def _remove_service_async(self):
        try:
            import subprocess
            import os
            import time

            subprocess.Popen(
                ["pkill", "-9", "-f", "main.py --daemon"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.Popen(
                ["pkill", "-9", "-f", "FelfelDM --daemon"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)

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

            service_path = os.path.expanduser("~/.config/systemd/user/felfeldm.service")
            if os.path.exists(service_path):
                os.remove(service_path)

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

            self._free_port(8765)

            QTimer.singleShot(1000, self._check_service_status)

            self.service_status.setText("✅ Service removed")
            self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

        except Exception as e:
            self.service_status.setText(f"❌ Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

    def _free_port(self, port):
        try:
            import subprocess
            import socket
            import time
            import os

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result != 0:
                return True

            print(f"🔍 Port {port} is in use, trying to free it...")

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
                        print(f"🔪 Killing process {pid} on port {port}")
                        subprocess.Popen(
                            ["kill", "-9", pid],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )

                time.sleep(1)

                sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock2.settimeout(1)
                result2 = sock2.connect_ex(("localhost", port))
                sock2.close()

                if result2 == 0:
                    print(f"⚠️ Port {port} still in use!")
                    return False
                else:
                    print(f"✅ Port {port} is free now")
                    return True

            except subprocess.TimeoutExpired:
                print(f"⚠️ Timeout checking port {port}")
                return False

        except Exception as e:
            print(f"❌ Error freeing port {port}: {e}")
            return False

    def _check_service_status(self):
        try:
            import subprocess
            import socket

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
                self.service_status.setText("✅ Service is active")
                self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
                self.run_as_service.setChecked(True)
            elif is_active:
                self.service_status.setText("⚠️ Service is active but not enabled")
                self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            else:
                self.service_status.setText("🔹 Service is removed")
                self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
                self.run_as_service.setChecked(False)

        except:
            self.service_status.setText("🔹 Service is removed")
            self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
            self.run_as_service.setChecked(False)

    def _toggle_global_speed(self, checked):
        self.global_speed_spin.setEnabled(checked)

    def _update_proxy_status(self):
        """Update proxy status display"""
        from core.proxy_manager import ProxyManager

        proxy_mgr = ProxyManager(
            self.parent().store if hasattr(self.parent(), "store") else None
        )

        if (
            proxy_mgr.global_proxy
            and proxy_mgr.global_proxy.enabled
            and proxy_mgr.global_proxy.host
        ):
            self.proxy_status_label.setText(
                f"✅ {proxy_mgr.global_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60;")
            self.proxy_info_label.setText(
                f"Type: {proxy_mgr.global_proxy.type.value.upper()} • {proxy_mgr.global_proxy.host}:{proxy_mgr.global_proxy.port}"
            )
        else:
            self.proxy_status_label.setText("⛔ Disabled")
            self.proxy_status_label.setStyleSheet("color: #95a5a6;")
            self.proxy_info_label.setText("No global proxy configured")

    def _configure_global_proxy(self):
        """Open proxy configuration dialog"""
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyManager

        if not hasattr(self.parent(), "store"):
            QMessageBox.warning(self, "Error", "Data store not available")
            return

        proxy_mgr = ProxyManager(self.parent().store)
        current_config = proxy_mgr.global_proxy or ProxyConfig()

        dlg = ProxyDialog(current_config, self, "Global Proxy Settings")
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            proxy_mgr.set_global_proxy(new_config)
            self._update_proxy_status()

            # Apply to aria2
            if hasattr(self.parent(), "aria2"):
                self.parent().aria2.set_global_proxy(new_config)

            QMessageBox.information(self, "Success", "Proxy settings applied!")

    def _update_service_status(self):
        QTimer.singleShot(100, self._check_service_status)

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
            "max_tries": self.max_tries.value(),
            "max_concurrent": self.max_concurrent.value(),
            "auto_clear_completed": self.auto_clear_completed.isChecked(),
            "theme": self.theme_combo.currentText().lower(),
            "run_as_service": self.run_as_service.isChecked(),
            "speed_limit": speed_limit,
        }


class YouTubeDownloadDialog(QDialog):
    youtube_download_requested = pyqtSignal(dict)

    def __init__(self, parent=None, queues=None, default_queue=0):
        super().__init__(parent)
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(550)

        self.queues = queues or []
        self.default_queue = default_queue

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # URL
        url_group = QGroupBox("YouTube URL")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.url_edit)

        self.fetch_btn = QPushButton("Get Video Info")
        self.fetch_btn.setIcon(get_icon("view-refresh"))
        self.fetch_btn.clicked.connect(self._fetch_info)
        url_layout.addWidget(self.fetch_btn)

        lay.addWidget(url_group)

        # Video Info
        info_group = QGroupBox("Video Info")
        self.info_layout = QFormLayout(info_group)
        self.info_layout.setSpacing(6)

        # Placeholder
        self.info_placeholder = QLabel("Enter a YouTube URL and click 'Get Video Info'")
        self.info_placeholder.setStyleSheet("color: #95a5a6; font-size: 11px;")
        self.info_layout.addRow(self.info_placeholder)

        lay.addWidget(info_group)

        # Options
        options_group = QGroupBox("Download Options")
        options_layout = QFormLayout(options_group)

        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        options_layout.addRow("Quality/Format:", self.format_combo)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_row.addWidget(self.path_edit)
        browse = QPushButton("Browse")
        browse.setIcon(get_icon("folder-open"))
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        options_layout.addRow("Save to:", path_row)

        cookie_row = QHBoxLayout()
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("Optional: Path to cookies.txt")
        cookie_row.addWidget(self.cookie_edit)
        cookie_browse = QPushButton("Browse")
        cookie_browse.setIcon(get_icon("folder-open"))
        cookie_browse.clicked.connect(self._browse_cookie)
        cookie_row.addWidget(cookie_browse)
        options_layout.addRow("Cookies:", cookie_row)

        # ===== بخش جدید: انتخاب صف =====
        queue_row = QHBoxLayout()
        self.queue_combo = QComboBox()

        # پر کردن صف‌ها
        for i, q in enumerate(self.queues):
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, i)

        # انتخاب صف پیش‌فرض
        if self.default_queue < self.queue_combo.count():
            self.queue_combo.setCurrentIndex(self.default_queue)

        queue_row.addWidget(self.queue_combo)
        options_layout.addRow("Add to Queue:", queue_row)

        lay.addWidget(options_group)

        # === Proxy Settings Group ===
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            [
                "Use Global Proxy",
                "Custom Proxy for this download",
                "No Proxy (Direct Connection)",
            ]
        )
        self.proxy_combo.setCurrentIndex(0)
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_layout.addWidget(self.proxy_combo)

        # Custom proxy config button
        proxy_btn_layout = QHBoxLayout()
        self.proxy_config_btn = QPushButton(
            get_icon("configure"), "Configure Custom Proxy"
        )
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        self.proxy_config_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), "Clear")
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        self.proxy_clear_btn.setEnabled(False)
        proxy_btn_layout.addWidget(self.proxy_clear_btn)
        proxy_btn_layout.addStretch()
        proxy_layout.addLayout(proxy_btn_layout)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setStyleSheet(
            "color: #95a5a6; font-size: 10px; padding: 2px;"
        )
        self.proxy_status_label.setWordWrap(True)
        proxy_layout.addWidget(self.proxy_status_label)

        lay.addWidget(proxy_group)

        # Buttons
        btn_box = QDialogButtonBox()
        self.download_btn = btn_box.addButton(
            "Add to Queue", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.download_btn.setIcon(get_icon("download"))
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_add_to_queue)

        cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setIcon(get_icon("dialog-cancel"))
        cancel_btn.clicked.connect(self.reject)

        lay.addWidget(btn_box)

        self.video_info = None
        self._custom_proxy = None
        self._format_map = {}
        self.worker = None

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _browse_cookie(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cookies File", "", "Cookies Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookie_edit.setText(file_path)

    def _on_proxy_mode_changed(self, index):
        """Enable/disable custom proxy config based on selection"""
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)

        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        """Open custom proxy configuration dialog"""
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
        """Clear custom proxy"""
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")
        self.proxy_status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")

    def _update_proxy_status(self):
        """Update status label with custom proxy info"""
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✅ Custom: {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 10px;")
        else:
            self.proxy_status_label.setText("⚠️ Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 10px;")

    def _get_proxy_url(self):
        """Get proxy URL based on selection"""
        proxy_mode = self.proxy_combo.currentIndex()

        if proxy_mode == 0:  # Use Global Proxy
            if hasattr(self.parent(), "proxy_manager"):
                proxy = self.parent().proxy_manager.get_proxy_for_queue(None)
                if proxy and proxy.is_valid():
                    return proxy._build_proxy_url()
        elif proxy_mode == 1:  # Custom Proxy
            if self._custom_proxy and self._custom_proxy.is_valid():
                return self._custom_proxy._build_proxy_url()
        return None

    def clear_info_layout(self):
        """Clear all widgets from info layout"""
        while self.info_layout.rowCount() > 0:
            self.info_layout.removeRow(self.info_layout.rowCount() - 1)

    def _fetch_info(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL")
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching...")

        # Clear previous info
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
            self.fetch_btn.setText("Get Video Info")

    def _on_info_fetched(self, info):
        """When video info is fetched"""
        self.video_info = info

        # Clear previous info
        self.clear_info_layout()

        # Title
        title = info.get("title", "Unknown")
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: 600;")
        self.info_layout.addRow("Title:", title_label)

        # Channel
        uploader = info.get("uploader", "Unknown")
        self.info_layout.addRow("Channel:", QLabel(uploader))

        # Duration
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
                    from utils.helpers import format_size

                    label += f" ({format_size(filesize)})"
                video_formats.append((format_id, label, f))

            elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                bitrate = f.get("abr")
                label = f"Audio ({ext.upper()})"
                if bitrate:
                    label += f" - {bitrate}kbps"
                if filesize:
                    from utils.helpers import format_size

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
            self.format_combo.insertItem(0, "Best Quality (Auto)", "best")

        self.format_combo.setCurrentIndex(0)

        if video_formats:
            quality_labels = [
                f"{f[2].get('resolution', 'Unknown')}" for f in video_formats[:5]
            ]
            self.info_layout.addRow("Qualities:", QLabel(", ".join(quality_labels)))

        # File size
        filesize = info.get("filesize")
        if filesize:
            from utils.helpers import format_size

            self.info_layout.addRow("Size:", QLabel(format_size(filesize)))

        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.download_btn.setText("Add to Queue")
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Video Info")

    def _on_info_fetch_finished(self, success, message):
        """When info fetch is finished"""
        if not success:
            self.clear_info_layout()
            self.info_placeholder = QLabel(f"Error: {message}")
            self.info_placeholder.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.info_layout.addRow(self.info_placeholder)
            self.download_btn.setEnabled(False)

        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Video Info")

    def _on_add_to_queue(self):
        """افزودن دانلود به صف"""
        data = self.get_data()

        if not data["url"]:
            QMessageBox.warning(self, "Error", "Please enter a valid YouTube URL")
            return

        # انتخاب صف
        queue_index = self.queue_combo.currentData()
        queue_name = self.queue_combo.currentText()

        # آماده‌سازی داده برای ارسال
        download_data = {
            "url": data["url"],
            "save_path": data["path"],
            "queue_id": queue_name,
            "download_type": "youtube",
            "yt_options": {
                "quality": data.get("quality", "best"),
                "format": data.get("format", "video"),
                "cookies_path": data.get("cookie_file"),
                "title": data.get("video_info", {}).get("title", ""),
                "format_id": data.get("format_id"),
                "format_info": data.get("format_info", {}),
            },
            "proxy": data.get("proxy_url"),
            "video_info": data.get("video_info"),
        }

        # ارسال سیگنال به parent
        self.youtube_download_requested.emit(download_data)
        self.accept()

    def get_data(self):
        """Get all dialog data"""
        proxy_mode = self.proxy_combo.currentIndex()

        selected_format_id = self.format_combo.currentData()
        format_type = "video"
        quality = "best"

        if selected_format_id == "best":
            quality = "best"
            format_type = "video"
        else:
            format_info = self._format_map.get(selected_format_id, {})
            ext = format_info.get("ext", "mp4")
            resolution = format_info.get("resolution", "")

            # تشخیص نوع (ویدیو یا صدا)
            if format_info.get("vcodec") and format_info.get("vcodec") != "none":
                format_type = "video"
                quality = resolution or "best"
            else:
                format_type = "audio"
                quality = format_info.get("abr", "best")

        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "format": format_type,
            "quality": quality,
            "format_id": selected_format_id,
            "format_info": self._format_map.get(selected_format_id, {}),
            "cookie_file": self.cookie_edit.text().strip() or None,
            "video_info": self.video_info,
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
            "proxy_url": self._get_proxy_url(),
            "queue_index": self.queue_combo.currentData(),
            "queue_name": self.queue_combo.currentText(),
        }


class ProxyDialog(QDialog):
    def __init__(
        self, proxy_config: ProxyConfig = None, parent=None, title="Proxy Settings"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)

        self.proxy_config = proxy_config or ProxyConfig()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        # Enable/Disable
        self.enable_cb = QCheckBox("Enable Proxy")
        self.enable_cb.setChecked(self.proxy_config.enabled)
        self.enable_cb.toggled.connect(self._toggle_enable)
        lay.addWidget(self.enable_cb)

        # Main form
        form_group = QGroupBox("Proxy Configuration")
        form_lay = QFormLayout(form_group)

        # Type
        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value.upper() for t in ProxyType])
        current_type = self.proxy_config.type.value.upper()
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        form_lay.addRow("Type:", self.type_combo)

        # Host
        self.host_edit = QLineEdit(self.proxy_config.host)
        self.host_edit.setPlaceholderText("proxy.example.com or 127.0.0.1")
        form_lay.addRow("Host:", self.host_edit)

        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.proxy_config.port)
        form_lay.addRow("Port:", self.port_spin)

        # Auth separator
        auth_label = QLabel("Authentication (optional)")
        auth_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
        form_lay.addRow(auth_label)

        # Username
        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username")
        form_lay.addRow("Username:", self.username_edit)

        # Password
        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")
        form_lay.addRow("Password:", self.password_edit)

        # Show/Hide password
        show_pwd = QPushButton(get_icon("view-show"), "")
        show_pwd.setFixedWidth(30)
        show_pwd.setToolTip("Show/Hide Password")
        show_pwd.clicked.connect(lambda: self._toggle_password_visibility())
        form_lay.addRow("", show_pwd)

        lay.addWidget(form_group)

        # Test button
        test_btn = QPushButton(get_icon("view-refresh"), "Test Proxy Connection")
        test_btn.clicked.connect(self._test_proxy)
        lay.addWidget(test_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        lay.addWidget(self.status_label)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

        self._toggle_enable(self.proxy_config.enabled)

    def _toggle_enable(self, checked):
        self.type_combo.setEnabled(checked)
        self.host_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)
        self.username_edit.setEnabled(checked)
        self.password_edit.setEnabled(checked)

    def _toggle_password_visibility(self):
        if self.password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _test_proxy(self):
        config = self.get_proxy_config()
        if not config.is_valid():
            self.status_label.setText("❌ Invalid proxy configuration")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return

        try:
            import requests

            proxy_url = config._build_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}

            self.status_label.setText("⏳ Testing connection...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()

            response = requests.get(
                "https://www.google.com", proxies=proxies, timeout=10
            )

            if response.status_code == 200:
                self.status_label.setText("✅ Proxy is working!")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(
                    f"⚠️ Proxy returned status: {response.status_code}"
                )
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")

        except requests.exceptions.Timeout:
            self.status_label.setText("❌ Connection timeout")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.ConnectionError as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:50]}")
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
        self.setWindowTitle("🛑 System Shutdown")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("⚠️ System Shutdown")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        msg = QLabel("All downloads are complete!\nThe system will shut down in:")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(msg)

        self.countdown_lbl = QLabel("20")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_lbl.setStyleSheet("font-size: 42px; font-weight: bold;")
        layout.addWidget(self.countdown_lbl)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(20)
        self.progress_bar.setValue(20)
        layout.addWidget(self.progress_bar)

        self.cancel_btn = QPushButton("Cancel Shutdown")
        self.cancel_btn.clicked.connect(self._on_cancel)
        layout.addWidget(self.cancel_btn)

        self._countdown = 20
        self._timer = None
        self._cancelled = False

    def start_countdown(self):
        self._countdown = 20
        self.countdown_lbl.setText("20")
        self.progress_bar.setValue(20)
        self._cancelled = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start(1000)

    def _update_countdown(self):
        """به‌روزرسانی شمارش معکوس"""
        self._countdown -= 1

        self.countdown_lbl.setText(str(self._countdown))
        self.progress_bar.setValue(self._countdown)

        if self._countdown <= 0:
            self._timer.stop()
            self._timer = None
            self.accept()

    def _on_cancel(self):
        """کنسل کردن خاموشی"""
        self._cancelled = True
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.reject()

    def is_cancelled(self):
        """بررسی اینکه کاربر کنسل کرده یا نه"""
        return self._cancelled

    def closeEvent(self, event):
        """وقتی دیالوگ بسته میشه"""
        if self._timer:
            self._timer.stop()
            self._timer = None
        event.accept()
