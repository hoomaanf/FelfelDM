# =============================================================================
# ui/dialogs.py
# =============================================================================
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt

import validators


def validate_download_path(path: str) -> Optional[str]:
    """Validate and sanitize a file path, ensuring it is within allowed base."""
    if not path or not path.strip():
        return None
    expanded = os.path.expanduser(path.strip())
    abs_path = os.path.abspath(expanded)
    allowed_base = os.path.expanduser("~/Downloads")
    if not abs_path.startswith(allowed_base):
        return None
    return abs_path


def is_valid_url(url: str) -> bool:
    """
    Validate URL or Magnet link.
    For HTTP/HTTPS: use validators.url.
    For Magnet: use comprehensive regex.
    """
    if not url:
        return False
    url = url.strip()

    # HTTP/HTTPS
    if url.startswith(("http://", "https://")):
        return validators.url(url)

    # Magnet: comprehensive check
    if url.startswith("magnet:?xt=urn:"):
        # Allow at least xt parameter, optionally other parameters
        pattern = re.compile(
            r'^magnet:\?xt=urn:[a-zA-Z0-9]+:[a-zA-Z0-9]+'
            r'(?:&[a-zA-Z0-9_]+=[^&]*)*$'
        )
        if pattern.match(url):
            return True
        # Allow simple magnet with just xt
        if re.match(r'^magnet:\?xt=urn:[a-zA-Z0-9]+:[a-zA-Z0-9]+$', url):
            return True
        return False

    return False


class AddDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Download")
        self.setModal(True)
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # URL input
        layout.addWidget(QLabel("URL or Magnet Link:"))
        self.url_edit = QLineEdit()
        layout.addWidget(self.url_edit)

        # Path selector
        layout.addWidget(QLabel("Save to:"))
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setText(str(Path.home() / "Downloads"))
        path_layout.addWidget(self.path_edit)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self.browse_path)
        path_layout.addWidget(self.browse_btn)
        layout.addLayout(path_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self.accept)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.add_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self._info = None

    def browse_path(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if dir_path:
            validated = validate_download_path(dir_path)
            if validated:
                self.path_edit.setText(validated)
            else:
                QMessageBox.warning(self, "Invalid Path", "Please select a folder inside Downloads.")

    def get_download_info(self) -> Optional[Dict[str, str]]:
        url = self.url_edit.text().strip()
        path = self.path_edit.text().strip()
        validated_path = validate_download_path(path)
        if not validated_path:
            QMessageBox.warning(self, "Invalid Path", "Save path is not valid.")
            return None
        if not is_valid_url(url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid URL or Magnet link.")
            return None
        return {"url": url, "path": validated_path}

    def accept(self):
        info = self.get_download_info()
        if info:
            self._info = info
            super().accept()

    def get_info(self) -> Optional[Dict[str, str]]:
        return self._info
