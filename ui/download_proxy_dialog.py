from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from core.proxy_manager import ProxyType, ProxyConfig
from utils.helpers import get_icon

class DownloadProxyDialog(QDialog):
    """Dialog for setting proxy per download"""
    
    def __init__(self, download_name: str, proxy_config: ProxyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Proxy for: {download_name}")
        self.setMinimumWidth(500)
        self.setModal(True)
        
        self.download_name = download_name
        self.proxy_config = proxy_config or ProxyConfig()
        
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel(f"⚙️ Proxy Settings for <b>{download_name}</b>")
        header.setStyleSheet("font-size: 14px;")
        lay.addWidget(header)
        
        info = QLabel("Configure a specific proxy for this download only.")
        info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        lay.addWidget(info)
        
        lay.addSpacing(10)
        
        # Proxy options
        self.use_global_cb = QRadioButton("Use Global/Queue Proxy")
        self.use_global_cb.setChecked(True)
        self.use_custom_cb = QRadioButton("Use Custom Proxy for this download only")
        self.use_custom_cb.toggled.connect(self._toggle_custom)
        
        lay.addWidget(self.use_global_cb)
        lay.addWidget(self.use_custom_cb)
        
        lay.addSpacing(5)
        
        # Custom proxy config
        self.proxy_group = QGroupBox("Custom Proxy Configuration")
        self.proxy_group.setEnabled(False)
        proxy_lay = QFormLayout(self.proxy_group)
        proxy_lay.setSpacing(8)
        
        # Type
        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value.upper() for t in ProxyType])
        current_type = self.proxy_config.type.value.upper()
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        proxy_lay.addRow("Type:", self.type_combo)
        
        # Host
        self.host_edit = QLineEdit(self.proxy_config.host)
        self.host_edit.setPlaceholderText("proxy.example.com or 127.0.0.1")
        proxy_lay.addRow("Host:", self.host_edit)
        
        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.proxy_config.port)
        proxy_lay.addRow("Port:", self.port_spin)
        
        # Auth
        proxy_lay.addRow(QLabel("Authentication (optional)"))
        
        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username (optional)")
        proxy_lay.addRow("Username:", self.username_edit)
        
        pwd_layout = QHBoxLayout()
        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password (optional)")
        pwd_layout.addWidget(self.password_edit)
        
        show_pwd = QPushButton()
        show_pwd.setIcon(get_icon('password-show-off')) 
        show_pwd.setFixedWidth(30)
        show_pwd.setFixedHeight(30)
        show_pwd.setToolTip("Show/Hide Password")
        show_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
        show_pwd.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(show_pwd)
        
        proxy_lay.addRow("Password:", pwd_layout)
        
        lay.addWidget(self.proxy_group)
        
        # Test button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton(get_icon('view-refresh'), "Test Proxy")
        self.test_btn.clicked.connect(self._test_proxy)
        test_layout.addWidget(self.test_btn)
        test_layout.addStretch()
        lay.addLayout(test_layout)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)
        
        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        
        apply_btn = btn_box.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.setText("Apply & Test")
        apply_btn.clicked.connect(self._apply_and_test)
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setStyleSheet("font-weight: bold;")
        
        lay.addWidget(btn_box)
        
        # If there's a custom config, enable it
        if self.proxy_config and self.proxy_config.host:
            self.use_custom_cb.setChecked(True)
            self.proxy_group.setEnabled(True)
    
    def _toggle_custom(self, checked):
        self.proxy_group.setEnabled(checked)
        if not checked:
            self.status_label.setText("")
    
    def _toggle_password_visibility(self):
        if self.password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.sender().setIcon(get_icon('password-show-on')) 
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.sender().setIcon(get_icon('password-show-off')) 
    
    def _test_proxy(self):
        """Test the custom proxy"""
        if not self.use_custom_cb.isChecked():
            self.status_label.setText("ℹ️ Using global/queue proxy")
            self.status_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
            return
        
        config = self._get_custom_config()
        if not config.is_valid():
            self.status_label.setText("❌ Invalid configuration (check host and port)")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return
        
        try:
            import requests
            proxy_url = config._build_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}
            
            self.status_label.setText("⏳ Testing...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            
            response = requests.get("https://www.google.com", proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                self.status_label.setText("✅ Proxy is working!")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(f"⚠️ Status: {response.status_code}")
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:60]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
    
    def _apply_and_test(self):
        """Apply settings and test"""
        if self.use_custom_cb.isChecked():
            config = self._get_custom_config()
            if config.is_valid():
                self._temp_config = config
                self.status_label.setText("✅ Settings applied. Testing...")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText("❌ Invalid configuration")
                self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
                return
        
        self._test_proxy()
    
    def _get_custom_config(self) -> ProxyConfig:
        type_str = self.type_combo.currentText().lower()
        return ProxyConfig(
            proxy_type=ProxyType(type_str),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text().strip() or None,
            enabled=True
        )
    
    def get_data(self) -> dict:
        """Return proxy settings data"""
        return {
            "use_custom": self.use_custom_cb.isChecked(),
            "config": self._get_custom_config() if self.use_custom_cb.isChecked() else None
        }
        
        
class SimpleProxyDialog(QDialog):
    """Simple dialog for configuring proxy (no mode selection)"""
    
    def __init__(self, download_name: str, proxy_config: ProxyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Proxy for: {download_name}")
        self.setMinimumWidth(450)
        self.setModal(True)
        
        self.proxy_config = proxy_config or ProxyConfig()
        
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header = QLabel(f"⚙️ Configure Proxy for <b>{download_name}</b>")
        header.setStyleSheet("font-size: 14px;")
        lay.addWidget(header)
        
        # Proxy config
        self.proxy_group = QGroupBox("Proxy Configuration")
        proxy_lay = QFormLayout(self.proxy_group)
        proxy_lay.setSpacing(8)
        
        # Type
        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value.upper() for t in ProxyType])
        current_type = self.proxy_config.type.value.upper()
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        proxy_lay.addRow("Type:", self.type_combo)
        
        # Host
        self.host_edit = QLineEdit(self.proxy_config.host)
        self.host_edit.setPlaceholderText("proxy.example.com or 127.0.0.1")
        proxy_lay.addRow("Host:", self.host_edit)
        
        # Port
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.proxy_config.port)
        proxy_lay.addRow("Port:", self.port_spin)
        
        # Auth
        proxy_lay.addRow(QLabel("Authentication (optional)"))
        
        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username (optional)")
        proxy_lay.addRow("Username:", self.username_edit)
        
        pwd_layout = QHBoxLayout()
        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password (optional)")
        pwd_layout.addWidget(self.password_edit)
        
        show_pwd = QPushButton()
        show_pwd.setIcon(get_icon('password-show-off'))
        show_pwd.setFixedWidth(30)
        show_pwd.setFixedHeight(30)
        show_pwd.setToolTip("Show/Hide Password")
        show_pwd.setCursor(Qt.CursorShape.PointingHandCursor)
        show_pwd.clicked.connect(self._toggle_password_visibility)
        pwd_layout.addWidget(show_pwd)
        
        proxy_lay.addRow("Password:", pwd_layout)
        
        lay.addWidget(self.proxy_group)
        
        # Test button
        test_layout = QHBoxLayout()
        self.test_btn = QPushButton(get_icon('view-refresh'), "Test Proxy")
        self.test_btn.clicked.connect(self._test_proxy)
        test_layout.addWidget(self.test_btn)
        test_layout.addStretch()
        lay.addLayout(test_layout)
        
        # Status
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        self.status_label.setWordWrap(True)
        lay.addWidget(self.status_label)
        
        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        
        apply_btn = btn_box.button(QDialogButtonBox.StandardButton.Apply)
        apply_btn.setText("Apply & Test")
        apply_btn.clicked.connect(self._apply_and_test)
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setStyleSheet("font-weight: bold;")
        
        lay.addWidget(btn_box)
    
    def _toggle_password_visibility(self):
        if self.password_edit.echoMode() == QLineEdit.EchoMode.Password:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self.sender().setIcon(get_icon('password-show-on')) 
        else:
            self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.sender().setIcon(get_icon('password-show-off')) 
    
    def _test_proxy(self):
        """Test the proxy"""
        if hasattr(self, '_temp_config') and self._temp_config:
            config = self._temp_config
        else:
            config = self._get_config()
        
        if not config.is_valid():
            self.status_label.setText("❌ Invalid configuration (check host and port)")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return
        
        try:
            import requests
            proxy_url = config._build_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}
            
            self.status_label.setText("⏳ Testing...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            
            response = requests.get("https://www.google.com", proxies=proxies, timeout=10)
            
            if response.status_code == 200:
                self.status_label.setText("✅ Proxy is working!")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(f"⚠️ Status: {response.status_code}")
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"❌ Error: {str(e)[:60]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
    
    def _apply_and_test(self):
        """Apply settings and test"""
        config = self._get_config()
        if config.is_valid():
            self._temp_config = config
            self.status_label.setText("✅ Settings applied. Testing...")
            self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            self._test_proxy()
        else:
            self.status_label.setText("❌ Invalid configuration")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
    
    def _get_config(self) -> ProxyConfig:
        type_str = self.type_combo.currentText().lower()
        return ProxyConfig(
            proxy_type=ProxyType(type_str),
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text().strip() or None,
            enabled=True
        )
    
    def get_proxy_config(self) -> ProxyConfig:
        """Get the configured proxy"""
        return self._get_config()