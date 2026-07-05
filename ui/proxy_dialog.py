from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from core.proxy_manager import ProxyType, ProxyConfig
from utils.helpers import get_icon

class ProxyDialog(QDialog):
    def __init__(self, proxy_config: ProxyConfig = None, parent=None, title="Proxy Settings"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setModal(True)
        
        self.proxy_config = proxy_config or ProxyConfig()
        
        # Main layout
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)
        
        # Enable/Disable
        self.enable_cb = QCheckBox("Enable Proxy")
        self.enable_cb.setChecked(self.proxy_config.enabled)
        self.enable_cb.toggled.connect(self._toggle_enable)
        lay.addWidget(self.enable_cb)
        
        # Main form
        form_group = QGroupBox("Proxy Configuration")
        form_lay = QFormLayout(form_group)
        form_lay.setSpacing(8)
        
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
        
        # Separator
        form_lay.addRow(QLabel(""))
        
        # Auth section
        auth_label = QLabel("Authentication (optional)")
        auth_label.setStyleSheet("font-weight: bold; color: #95a5a6;")
        form_lay.addRow(auth_label)
        
        # Username
        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username (optional)")
        form_lay.addRow("Username:", self.username_edit)
        
        # Password with show/hide
        pwd_layout = QHBoxLayout()
        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password (optional)")
        pwd_layout.addWidget(self.password_edit)
        
        show_pwd = QPushButton()
        show_pwd.setIcon(get_icon('view-show'))
        show_pwd.setFixedWidth(30)
        show_pwd.setFixedHeight(30)
        show_pwd.setToolTip("Show/Hide Password")
        show_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
        show_pwd.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(show_pwd)
        
        form_lay.addRow("Password:", pwd_layout)
        
        lay.addWidget(form_group)
        
        # Info label
        info_label = QLabel("💡 Proxy will be used for all downloads (HTTP, HTTPS, FTP)")
        info_label.setStyleSheet("color: #95a5a6; font-size: 10px; padding: 4px;")
        lay.addWidget(info_label)
        
        # Test button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton(get_icon('view-refresh'), "Test Proxy Connection")
        self.test_btn.clicked.connect(self._test_proxy)
        self.test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_layout.addWidget(self.test_btn)
        test_layout.addStretch()
        lay.addLayout(test_layout)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)
        
        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        
        # Make OK button primary
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setStyleSheet("font-weight: bold;")
        
        lay.addWidget(btn_box)
        
        self._toggle_enable(self.proxy_config.enabled)
    
    def _toggle_enable(self, checked):
        """Enable/disable proxy fields"""
        self.type_combo.setEnabled(checked)
        self.host_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)
        self.username_edit.setEnabled(checked)
        self.password_edit.setEnabled(checked)
        
        if not checked:
            self.status_label.setText("")
    
    def _toggle_password_visibility(self):
        """Toggle password visibility"""
        if self.password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.sender().setIcon(get_icon('view-hide'))
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.sender().setIcon(get_icon('view-show'))
    
    def _test_proxy(self):
        """Test proxy connection"""
        config = self.get_proxy_config()
        
        if not config.enabled:
            self.status_label.setText("⏸ Proxy is disabled")
            self.status_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
            return
        
        if not config.is_valid():
            self.status_label.setText("❌ Invalid proxy configuration (check host and port)")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return
        
        try:
            import requests
            
            proxy_url = config._build_proxy_url()
            proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            
            self.status_label.setText("⏳ Testing connection to google.com...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            
            # Test with google.com
            response = requests.get(
                "https://www.google.com",
                proxies=proxies,
                timeout=10,
                verify=True
            )
            
            if response.status_code == 200:
                self.status_label.setText("✅ Proxy is working! Connection successful.")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(f"⚠️ Proxy returned status: {response.status_code}")
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
                
        except requests.exceptions.Timeout:
            self.status_label.setText("❌ Connection timeout - proxy is not responding")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.ProxyError as e:
            self.status_label.setText(f"❌ Proxy error: {str(e)[:60]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.ConnectionError as e:
            self.status_label.setText(f"❌ Connection failed: {str(e)[:60]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.SSLError:
            self.status_label.setText("❌ SSL error - try using HTTP proxy or disable SSL verification")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:60]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
    
    def get_proxy_config(self) -> ProxyConfig:
        """Get proxy configuration from dialog"""
        type_str = self.type_combo.currentText().lower()
        proxy_type = ProxyType(type_str)
        
        return ProxyConfig(
            proxy_type=proxy_type,
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text().strip() or None,
            enabled=self.enable_cb.isChecked()
        )


class QueueProxyDialog(QDialog):
    """Dialog for setting proxy per queue"""
    def __init__(self, queue_name: str, proxy_config: ProxyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Queue Proxy: {queue_name}")
        self.setMinimumWidth(450)
        self.setModal(True)
        
        self.queue_name = queue_name
        self.proxy_config = proxy_config or ProxyConfig()
        
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)
        
        # Info
        info = QLabel(f"Configure proxy specifically for queue: <b>{queue_name}</b>")
        info.setWordWrap(True)
        lay.addWidget(info)
        
        info2 = QLabel("This will override the global proxy for this queue only.")
        info2.setStyleSheet("color: #95a5a6; font-size: 11px;")
        lay.addWidget(info2)
        
        lay.addSpacing(10)
        
        # Use existing ProxyDialog
        self.proxy_dialog = ProxyDialog(proxy_config, self, f"Proxy for {queue_name}")
        # We'll just use the same fields as ProxyDialog
        # Reuse the same logic
        self.proxy_dialog.setParent(self)
        
        # Copy widgets from ProxyDialog
        self.enable_cb = self.proxy_dialog.enable_cb
        self.type_combo = self.proxy_dialog.type_combo
        self.host_edit = self.proxy_dialog.host_edit
        self.port_spin = self.proxy_dialog.port_spin
        self.username_edit = self.proxy_dialog.username_edit
        self.password_edit = self.proxy_dialog.password_edit
        self.status_label = self.proxy_dialog.status_label
        
        # Buttons
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        
        lay.addWidget(self.proxy_dialog)
        lay.addWidget(btn_box)
    
    def get_proxy_config(self) -> ProxyConfig:
        return self.proxy_dialog.get_proxy_config()