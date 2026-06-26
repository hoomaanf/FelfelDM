import os
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from utils.helpers import get_icon
from core.queue_model import Queue
from datetime import datetime, time as dtime

class AddDownloadDialog(QDialog):
    def __init__(self, queues, default_queue=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Downloads")
        self.setMinimumWidth(580)
        self.setMinimumHeight(400)

        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        url_group = QGroupBox("URLs")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        url_layout.addWidget(self.url_edit)

        import_btn = QPushButton(get_icon('document-open'), "Import from File")
        import_btn.clicked.connect(self._import_from_txt)
        url_layout.addWidget(import_btn)
        lay.addWidget(url_group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse...")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self.queue_cb = QComboBox()
        for q in queues:
            self.queue_cb.addItem(q.name)
        self.queue_cb.setCurrentIndex(default_queue)
        options_layout.addRow("Queue:", self.queue_cb)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        options_layout.addRow("Connections:", self.conn_spin)
        lay.addWidget(options_group)

        info_label = QLabel("ℹ️ Downloads will be added in Paused state")
        info_label.setStyleSheet("color: #95a5a6; font-size: 10px; padding: 4px;")
        lay.addWidget(info_label)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory", self.path_edit.text())
        if d: self.path_edit.setText(d)

    def _import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Links File", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    current_text = self.url_edit.toPlainText().strip()
                    combined = current_text + "\n" + "\n".join(lines) if current_text else "\n".join(lines)
                    self.url_edit.setPlainText(combined)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse file:\n{str(e)}")

    def get_data(self):
        raw_text = self.url_edit.toPlainText()
        urls = [line.strip() for line in raw_text.split('\n') if line.strip()]
        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "queue": self.queue_cb.currentIndex(),
            "connections": self.conn_spin.value(),
        }


class SingleDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Single Download")
        self.setMinimumWidth(500)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        url_group = QGroupBox("URL")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        url_layout.addWidget(self.url_edit)
        lay.addWidget(url_group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

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

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory", self.path_edit.text())
        if d: self.path_edit.setText(d)

    def get_data(self):
        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
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
        browse = QPushButton(get_icon('folder-open'), "Browse...")
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
        self.start_time = QTimeEdit(QTime(queue.schedule_start.hour, queue.schedule_start.minute))
        self.end_time = QTimeEdit(QTime(queue.schedule_end.hour, queue.schedule_end.minute))
        time_row.addWidget(QLabel("From:"))
        time_row.addWidget(self.start_time)
        time_row.addWidget(QLabel("To:"))
        time_row.addWidget(self.end_time)
        lay.addRow("Time Window:", time_row)

        days_row = QHBoxLayout()
        self.day_checks = []
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            cb = QCheckBox(d)
            cb.setChecked(i in queue.days)
            self.day_checks.append(cb)
            days_row.addWidget(cb)
        lay.addRow("Active Days:", days_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addRow(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory", self.path_edit.text())
        if d: self.path_edit.setText(d)

    def get_queue_data(self):
        st, en = self.start_time.time(), self.end_time.time()
        return {
            "name": self.name_edit.text().strip(),
            "save_path": self.path_edit.text().strip(),
            "max_concurrent": self.conc_spin.value(),
            "schedule_enabled": self.sched_cb.isChecked(),
            "schedule_start": dtime(st.hour(), st.minute()),
            "schedule_end": dtime(en.hour(), en.minute()),
            "days": [i for i, cb in enumerate(self.day_checks) if cb.isChecked()],
        }


class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

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

        dl_group = QGroupBox("Download")
        dl_layout = QFormLayout(dl_group)

        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 50)
        self.max_concurrent.setValue(settings.get("max_concurrent", 5))
        dl_layout.addRow("Max Concurrent Downloads:", self.max_concurrent)

        self.max_tries = QSpinBox()
        self.max_tries.setRange(0, 100)
        self.max_tries.setSpecialValueText("Unlimited")
        self.max_tries.setValue(settings.get("max_tries", 0))
        dl_layout.addRow("Max Retry Attempts:", self.max_tries)

        self.conns = QSpinBox()
        self.conns.setRange(1, 16)
        self.conns.setValue(settings.get("connections", 8))
        dl_layout.addRow("Default Connections:", self.conns)

        lay.addWidget(dl_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)
        cleanup_group = QGroupBox("Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        
        self.auto_clear_completed = QCheckBox("Auto-clear completed downloads when finished")
        self.auto_clear_completed.setChecked(settings.get("auto_clear_completed", False))
        cleanup_layout.addWidget(self.auto_clear_completed)
        
        lay.addWidget(cleanup_group)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

   
    def get_settings(self):
        return {
            "aria2_host": self.host.text().strip(),
            "aria2_port": self.port.value(),
            "aria2_secret": self.secret.text(),
            "connections": self.conns.value(),
            "max_tries": self.max_tries.value(),
            "max_concurrent": self.max_concurrent.value(),
            "auto_clear_completed": self.auto_clear_completed.isChecked(),
        }