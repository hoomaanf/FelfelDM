# ui/dialogs.py

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
            if q.name != "__direct__":
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
  
class QuickDownloadDialog(QDialog):
     def __init__(self, parent=None):
         super().__init__(parent)
         self.setWindowTitle("Download")
         self.setMinimumWidth(500)
         lay = QVBoxLayout(self)
         url_group = QGroupBox("URLs")
         url_layout = QVBoxLayout(url_group)
         self.url_edit = QTextEdit()
         self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
         self.url_edit.setMinimumHeight(80)
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
         self.conn_spin = QSpinBox()
         self.conn_spin.setRange(1, 16)
         self.conn_spin.setValue(8)
         form = QFormLayout()
         form.addRow("Connections:", self.conn_spin)
         lay.addLayout(form)
         btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
         btn_box.accepted.connect(self.accept)
         btn_box.rejected.connect(self.reject)
         lay.addWidget(btn_box)
     def _browse(self):
         d = QFileDialog.getExistingDirectory(self, "Select Directory", self.path_edit.text())
         if d:
             self.path_edit.setText(d)
     def get_data(self):
         raw = self.url_edit.toPlainText()
         urls = [l.strip() for l in raw.split('\n') if l.strip()]
         return {
             "urls": urls,
             "path": self.path_edit.text().strip(),
             "connections": self.conn_spin.value(),
         }
         
class DownloadProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)

    def __init__(self, gid, dl_data, parent=None):
        super().__init__(parent)
        self.gid = gid
        self.setWindowTitle("Download")
        self.setMinimumWidth(480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        self.name_lbl = QLabel(dl_data.get("name", "Unknown"))
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        lay.addWidget(self.name_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        lay.addWidget(self.progress_bar)

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
        self.pause_btn = QPushButton(get_icon('media-playback-pause'), "Pause")
        self.resume_btn = QPushButton(get_icon('media-playback-start'), "Resume")
        self.cancel_btn = QPushButton(get_icon('edit-delete'), "Cancel")
        self.pause_btn.clicked.connect(lambda: self.pause_requested.emit(self.gid))
        self.resume_btn.clicked.connect(lambda: self.resume_requested.emit(self.gid))
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.gid))
        btn_lay.addWidget(self.pause_btn)
        btn_lay.addWidget(self.resume_btn)
        btn_lay.addStretch()
        btn_lay.addWidget(self.cancel_btn)
        lay.addLayout(btn_lay)

        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        lay.addWidget(close_btn)

        self.update_data(dl_data)

    def update_data(self, dl_data):
        from utils.helpers import format_size, format_speed

        total = int(dl_data.get("totalLength", 0))
        completed = int(dl_data.get("completedLength", 0))
        speed = int(dl_data.get("downloadSpeed", 0))
        status = dl_data.get("status", "unknown")
        name = dl_data.get("name", "")
        if name:
            self.name_lbl.setText(name)

        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(pct)
            self.progress_bar.setFormat(f"{pct}%")
            self.size_lbl.setText(f"{format_size(completed)} / {format_size(total)}")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("—")
            self.size_lbl.setText(f"{format_size(completed)} / Unknown")

        self.speed_lbl.setText(format_speed(speed) if speed > 0 else "—")
        self.conn_lbl.setText(str(dl_data.get("connections", 0)))
        self.status_lbl.setText(status.capitalize())

        if speed > 0 and total > completed:
            eta_sec = (total - completed) // speed
            h, m, s = eta_sec // 3600, (eta_sec % 3600) // 60, eta_sec % 60
            self.eta_lbl.setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.eta_lbl.setText("—")

        self.pause_btn.setEnabled(status == "active")
        self.resume_btn.setEnabled(status == "paused")
        self.cancel_btn.setEnabled(status not in ["complete", "removed"])

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

        # === Cleanup ===
        cleanup_group = QGroupBox("Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        self.auto_clear_completed = QCheckBox("Auto-clear completed downloads")
        self.auto_clear_completed.setChecked(settings.get("auto_clear_completed", False))
        cleanup_layout.addWidget(self.auto_clear_completed)
        lay.addWidget(cleanup_group)

        # === Service ===
        service_group = QGroupBox("Service")
        service_layout = QVBoxLayout(service_group)
        
        self.run_as_service = QCheckBox("Run as background service (auto-start on login)")
        self.run_as_service.setChecked(settings.get("run_as_service", False))
        self.run_as_service.toggled.connect(self._on_service_toggle)
        service_layout.addWidget(self.run_as_service)
        
        self.service_status = QLabel("")
        self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        service_layout.addWidget(self.service_status)
        
        lay.addWidget(service_group)

        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
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
        """Handle service toggle - نصب یا حذف کامل سرویس"""
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
        """نصب کامل سرویس با مدیریت پورت"""
        try:
            import subprocess
            import os
            import time
            
            # مسیر اجرایی
            import sys
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                exe_path = "/usr/local/bin/FelfelDM"
            
            # 🔥 1. چک کردن و آزاد کردن پورت 8765
            self._free_port(8765)
            
            # 2. ایجاد پوشه سرویس
            service_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(service_dir, exist_ok=True)
            
            # 3. فایل سرویس
            service_content = f'''[Unit]
Description=FelfelDM Download Manager Service
After=network.target

[Service]
Type=simple
ExecStart={exe_path} --daemon
Restart=on-failure
RestartSec=10
TimeoutStopSec=10
WorkingDirectory=/usr/share/felfeldm
StandardOutput=journal
StandardError=journal
KillMode=process
KillSignal=SIGTERM

[Install]
WantedBy=default.target
'''
            
            service_path = os.path.join(service_dir, "felfeldm.service")
            with open(service_path, 'w') as f:
                f.write(service_content)
            
            # 4. ری‌لود systemd
            subprocess.Popen(['systemctl', '--user', 'daemon-reload'], 
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 5. فعال کردن سرویس
            subprocess.Popen(['systemctl', '--user', 'enable', 'felfeldm.service'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 6. شروع سرویس
            subprocess.Popen(['systemctl', '--user', 'start', 'felfeldm.service'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 7. صبر برای شروع
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
        """حذف کامل سرویس با کشتن پروسه"""
        try:
            import subprocess
            import os
            import time
            
            # 🔥 1. کشتن پروسه‌های باقی‌مانده
            subprocess.Popen(['pkill', '-9', '-f', 'main.py --daemon'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.Popen(['pkill', '-9', '-f', 'FelfelDM --daemon'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 2. متوقف کردن سرویس
            subprocess.Popen(['systemctl', '--user', 'stop', 'felfeldm.service'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 3. غیرفعال کردن
            subprocess.Popen(['systemctl', '--user', 'disable', 'felfeldm.service'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 4. حذف فایل سرویس
            service_path = os.path.expanduser("~/.config/systemd/user/felfeldm.service")
            if os.path.exists(service_path):
                os.remove(service_path)
            
            # 5. ری‌لود systemd
            subprocess.Popen(['systemctl', '--user', 'daemon-reload'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            
            # 6. ری‌ست failed state
            subprocess.Popen(['systemctl', '--user', 'reset-failed'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # 7. چک کن پورت آزاد شده
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
            
            # تست اینکه پورت در حال استفاده است
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()
            
            if result != 0:
                return True
            
            print(f"🔍 Port {port} is in use, trying to free it...")
            
            # پیدا کردن PID استفاده‌کننده از پورت
            try:
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True, text=True, timeout=2
                )
                pids = result.stdout.strip().split('\n')
                current_pid = str(os.getpid())  # 🔥 PID خود برنامه
                
                for pid in pids:
                    if pid and pid.isdigit() and pid != current_pid:  # 🔥 خودش رو نادیده بگیر
                        print(f"🔪 Killing process {pid} on port {port}")
                        subprocess.Popen(['kill', '-9', pid],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # صبر برای آزاد شدن پورت
                time.sleep(1)
                
                # چک مجدد
                sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock2.settimeout(1)
                result2 = sock2.connect_ex(('localhost', port))
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
        """بررسی وضعیت سرویس و آپدیت UI"""
        try:
            import subprocess
            import socket
            
            # 1. چک کردن سرویس
            result = subprocess.run(
                ['systemctl', '--user', 'is-active', 'felfeldm.service'],
                capture_output=True, text=True, timeout=2
            )
            is_active = result.stdout.strip() == 'active'
            
            # 2. چک کردن enabled
            result2 = subprocess.run(
                ['systemctl', '--user', 'is-enabled', 'felfeldm.service'],
                capture_output=True, text=True, timeout=2
            )
            is_enabled = result2.stdout.strip() == 'enabled'
            
            # 3. چک کردن پورت
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            port_open = sock.connect_ex(('localhost', 8765)) == 0
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

    def _update_service_status(self):
        """آپدیت اولیه وضعیت سرویس"""
        QTimer.singleShot(100, self._check_service_status)

    def get_settings(self):
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
        }

class YouTubeDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(550)
        
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        
        # URL
        url_group = QGroupBox("YouTube URL")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_layout.addWidget(self.url_edit)
        
        self.fetch_btn = QPushButton("Get Video Info")
        self.fetch_btn.setIcon(get_icon('view-refresh'))
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
        self.format_combo.addItems([
            "Video (MP4) - Best",
            "Video (MP4) - 1080p",
            "Video (MP4) - 720p",
            "Video (WebM)",
            "Audio (MP3)",
            "Audio (M4A)",
        ])
        self.format_combo.setEnabled(False)
        options_layout.addRow("Format:", self.format_combo)
        
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_row.addWidget(self.path_edit)
        browse = QPushButton("Browse")
        browse.setIcon(get_icon('folder-open'))
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        options_layout.addRow("Save to:", path_row)
        
        cookie_row = QHBoxLayout()
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("Optional: Path to cookies.txt")
        cookie_row.addWidget(self.cookie_edit)
        cookie_browse = QPushButton("Browse")
        cookie_browse.setIcon(get_icon('folder-open'))
        cookie_browse.clicked.connect(self._browse_cookie)
        cookie_row.addWidget(cookie_browse)
        options_layout.addRow("Cookies:", cookie_row)
        
        lay.addWidget(options_group)
        
        # Buttons
        btn_box = QDialogButtonBox()
        self.download_btn = btn_box.addButton("Download", QDialogButtonBox.ButtonRole.AcceptRole)
        self.download_btn.setIcon(get_icon('download'))
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self.accept)
        
        cancel_btn = btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        cancel_btn.setIcon(get_icon('dialog-cancel'))
        cancel_btn.clicked.connect(self.reject)
        
        lay.addWidget(btn_box)
        
        self.video_info = None
    
    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Directory", self.path_edit.text())
        if d:
            self.path_edit.setText(d)
    
    def _browse_cookie(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cookies File", "",
            "Cookies Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookie_edit.setText(file_path)
    
    def _fetch_info(self):
        url = self.url_edit.text().strip()
        if not url:
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
            
            self.worker = YouTubeWorker(url, "", "mp4", cookie_file)
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

    def clear_info_layout(self):
        """Clear all widgets from info layout"""
        while self.info_layout.rowCount() > 0:
            # Remove the last row
            self.info_layout.removeRow(self.info_layout.rowCount() - 1)

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
        
        # Resolutions
        formats = info.get("formats", [])
        resolutions = set()
        for f in formats:
            if f.get("resolution") and f.get("resolution") != "audio only":
                resolutions.add(f.get("resolution"))
        
        if resolutions:
            self.info_layout.addRow("Qualities:", QLabel(", ".join(sorted(resolutions))))
        
        # File size
        filesize = info.get("filesize")
        if filesize:
            from utils.helpers import format_size
            self.info_layout.addRow("Size:", QLabel(format_size(filesize)))
        
        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)
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
    
    def get_data(self):
        format_map = {
            0: "mp4",
            1: "mp4",
            2: "mp4",
            3: "webm",
            4: "mp3",
            5: "m4a",
        }
        
        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "format": format_map.get(self.format_combo.currentIndex(), "mp4"),
            "format_name": self.format_combo.currentText(),
            "cookie_file": self.cookie_edit.text().strip() or None,
            "video_info": self.video_info,
        }