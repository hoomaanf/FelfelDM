# ui/update_dialog.py

import os
import subprocess
import tempfile
import threading
import time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from utils.helpers import get_icon


class UpdateDialog(QDialog):
    
    update_finished = pyqtSignal(bool, str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Updating FelfelDM")
        self.setFixedSize(400, 150)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        
        self._is_updating = False
        self._is_cancelled = False
        self._process = None
        self._temp_script = None
        
        self._setup_ui()
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ===== عنوان =====
        title = QLabel("Updating FelfelDM...")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        layout.addWidget(title)
        
        # ===== Progress Bar =====
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.progress_bar.setFixedHeight(20)
        layout.addWidget(self.progress_bar)
        
        # ===== Status =====
        self.status_label = QLabel("Starting...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        layout.addWidget(self.status_label)
        
        layout.addSpacing(5)
        
        # ===== دکمه Cancel =====
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        self.update_finished.connect(self._on_update_finished)
        
        QTimer.singleShot(100, self._start_update)
        
    def _start_update(self):
        if self._is_updating:
            return
        
        self._is_updating = True
        self._is_cancelled = False
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setText("Cancel")
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting update...")
        
        thread = threading.Thread(target=self._update_thread, daemon=True)
        thread.start()
        
    def _update_thread(self):
        try:
            self._temp_script = tempfile.NamedTemporaryFile(
                mode='w', suffix='.sh', delete=False
            )
            self._temp_script.write("""#!/bin/bash
echo "10% - Downloading..."
curl -s -o /tmp/felfeldm_install.sh https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh
echo "30% - Preparing..."
chmod +x /tmp/felfeldm_install.sh
echo "50% - Installing..."
bash /tmp/felfeldm_install.sh
echo "90% - Cleaning up..."
rm -f /tmp/felfeldm_install.sh
echo "100% - Done!"
""")
            self._temp_script.close()
            os.chmod(self._temp_script.name, 0o755)
            
            self._process = subprocess.Popen(
                ["pkexec", "bash", self._temp_script.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in self._process.stdout:
                if self._is_cancelled:
                    break
                line = line.strip()
                if line and "%" in line:
                    try:
                        pct = int(line.split("%")[0].strip())
                        self._update_progress(pct, line)
                    except:
                        pass
            
            if self._is_cancelled:
                self._kill_process()
                self.update_finished.emit(False, "Update cancelled by user")
            elif self._process.returncode == 0:
                self.update_finished.emit(True, "Update completed!")
            else:
                self.update_finished.emit(False, f"Update failed with code {self._process.returncode}")
                
        except Exception as e:
            if not self._is_cancelled:
                self.update_finished.emit(False, f"Error: {str(e)}")
            
        finally:
            if self._temp_script:
                try:
                    os.unlink(self._temp_script.name)
                except:
                    pass
    
    def _kill_process(self):
        try:
            if self._process:
                self._process.kill()
                self._process.wait()
        except:
            pass
        
        # ===== pkill با ignore error =====
        try:
            subprocess.run(["pkill", "-9", "-f", "felfeldm_install.sh"], 
                          capture_output=True, stderr=subprocess.DEVNULL)
        except:
            pass
            
        try:
            subprocess.run(["pkill", "-9", "-f", "pkexec"], 
                          capture_output=True, stderr=subprocess.DEVNULL)
        except:
            pass
        
        print("✅ Cancel requested")
    
    def _update_progress(self, value: int, message: str):
        QMetaObject.invokeMethod(
            self,
            "_do_update_progress",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(int, value),
            Q_ARG(str, message)
        )
    
    @pyqtSlot(int, str)
    def _do_update_progress(self, value: int, message: str):
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    @pyqtSlot(bool, str)
    def _on_update_finished(self, success: bool, message: str):
        self._is_updating = False
        self.cancel_btn.setEnabled(True)
        
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("✅ Update completed!")
            self.status_label.setStyleSheet("color: #27ae60; font-size: 12px;")
            self.cancel_btn.setText("Close")
            self.cancel_btn.clicked.disconnect()
            self.cancel_btn.clicked.connect(self.accept)
            
            reply = QMessageBox.question(
                self,
                "Restart Required",
                "Update completed!\n\nRestart FelfelDM now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self._restart_application()
            else:
                self.accept()
                
        else:
            self.progress_bar.setValue(0)
            self.status_label.setText(f"❌ {message}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 12px;")
            self.cancel_btn.setText("Close")
            self.cancel_btn.clicked.disconnect()
            self.cancel_btn.clicked.connect(self.accept)
            
            if "cancelled" not in message.lower():
                QMessageBox.warning(self, "Update Failed", message)
    
    def _restart_application(self):
        import sys
        import subprocess
        
        try:
            self.close()
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable])
            else:
                subprocess.Popen([sys.executable, "main.py"])
            QApplication.quit()
        except:
            QMessageBox.warning(self, "Error", "Could not restart automatically.")
            self.close()
    
    def _on_cancel_clicked(self):
        if self._is_updating:
            reply = QMessageBox.question(
                self,
                "Cancel Update",
                "Are you sure you want to cancel the update?\n\nThe update is currently in progress.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._is_cancelled = True
                self.cancel_btn.setEnabled(False)
                self.cancel_btn.setText("Cancelling...")
                self.status_label.setText("Cancelling update...")
                
                self._kill_process()
                
                QTimer.singleShot(1000, lambda: self.update_finished.emit(False, "Update cancelled by user"))
        else:
            self.reject()
    
    def closeEvent(self, event):
        if self._is_updating:
            reply = QMessageBox.question(
                self,
                "Cancel Update",
                "Update is still running. Cancel?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._is_cancelled = True
                self._kill_process()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def show_update_dialog(parent=None):
    dialog = UpdateDialog(parent)
    return dialog.exec()