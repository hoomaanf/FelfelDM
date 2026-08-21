# ui/export_dialog.py

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from typing import List
import os


class ExportDialog(QDialog):
    def __init__(self, queues: List, parent=None):
        super().__init__(parent)
        self.queues = queues
        self.setWindowTitle("Export Downloads")
        self.setMinimumWidth(500)
        self.setModal(True)

        self.selected_queue = None
        self.selected_format = "urls_only"
        self.selected_path = ""
        self.include_headers = True

        self._init_ui()
        self._set_default_path()
        self._center_on_parent()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ===== انتخاب صف =====
        layout.addWidget(QLabel("Select Queue:"))
        self.queue_combo = QComboBox()

        # فیلتر صف‌های معتبر (به جز __direct__)
        valid_queues = [q for q in self.queues if q.name != "__direct__"]
        for q in valid_queues:
            count = len(q.downloads)
            self.queue_combo.addItem(f"{q.name} ({count} downloads)", q)

        if valid_queues:
            self.queue_combo.setCurrentIndex(0)
            self.selected_queue = valid_queues[0]

        self.queue_combo.currentIndexChanged.connect(self._on_queue_changed)
        layout.addWidget(self.queue_combo)

        layout.addSpacing(8)

        # ===== انتخاب فرمت =====
        layout.addWidget(QLabel("Export Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(
            [
                "URLs Only (TXT)",
                "URLs + Names (CSV)",
                "Full Details (JSON)",
                "Full Details (CSV)",
                "Full Details (HTML)",
                "Copy to Clipboard",
            ]
        )
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        layout.addWidget(self.format_combo)

        layout.addSpacing(8)

        # ===== گزینه‌ها =====
        self.header_cb = QCheckBox("Include headers (Name, URL, Status, Size)")
        self.header_cb.setChecked(True)
        self.header_cb.setEnabled(False)  # فقط برای CSV/HTML فعال میشه
        layout.addWidget(self.header_cb)

        # ===== انتخاب مسیر =====
        path_group = QGroupBox("Save Location")
        path_layout = QVBoxLayout(path_group)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        path_row.addWidget(self.path_edit)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.browse_btn)

        path_layout.addLayout(path_row)
        layout.addWidget(path_group)

        layout.addSpacing(8)

        # ===== دکمه‌ها =====
        btn_layout = QHBoxLayout()
        self.export_btn = QPushButton("Export")
        self.export_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.export_btn.clicked.connect(self.accept)
        self.export_btn.setEnabled(False)

        self.copy_btn = QPushButton("Copy to Clipboard")
        self.copy_btn.setIcon(QIcon.fromTheme("edit-copy"))
        self.copy_btn.clicked.connect(lambda: self._set_copy_mode())
        self.copy_btn.setVisible(False)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addWidget(self.export_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        # به‌روزرسانی اولیه
        self._on_format_changed(0)

    def _on_queue_changed(self, index):
        if index >= 0:
            self.selected_queue = self.queue_combo.currentData()
            self._update_path()

    def _on_format_changed(self, index):
        format_text = self.format_combo.currentText()

        # نمایش/مخفی کردن دکمه‌ها
        if "Clipboard" in format_text:
            self.browse_btn.setEnabled(False)
            self.path_edit.setEnabled(False)
            self.export_btn.setVisible(False)
            self.copy_btn.setVisible(True)
            self.header_cb.setEnabled(True)
        else:
            self.browse_btn.setEnabled(True)
            self.path_edit.setEnabled(True)
            self.export_btn.setVisible(True)
            self.copy_btn.setVisible(False)
            self.header_cb.setEnabled(True)

        # فعال/غیرفعال کردن هدر
        if "URLs Only" in format_text:
            self.header_cb.setEnabled(False)
            self.header_cb.setChecked(False)
        else:
            self.header_cb.setEnabled(True)
            self.header_cb.setChecked(True)

        self._update_path()

    def _update_path(self):
        if not self.selected_queue:
            return

        format_text = self.format_combo.currentText()
        if "Clipboard" in format_text:
            self.path_edit.setText("(Will be copied to clipboard)")
            self.export_btn.setEnabled(True)
            return

        ext = {
            "URLs Only (TXT)": "txt",
            "URLs + Names (CSV)": "csv",
            "Full Details (JSON)": "json",
            "Full Details (CSV)": "csv",
            "Full Details (HTML)": "html",
        }.get(format_text, "txt")

        queue_name = self.selected_queue.name
        home = os.path.expanduser("~")
        base_name = f"{queue_name}_downloads"

        path = os.path.join(home, f"{base_name}.{ext}")

        # شماره‌گذاری
        counter = 1
        while os.path.exists(path):
            path = os.path.join(home, f"{base_name}_{counter}.{ext}")
            counter += 1

        self.path_edit.setText(path)
        self.export_btn.setEnabled(True)

    def _set_default_path(self):
        self._update_path()

    def _browse(self):
        format_text = self.format_combo.currentText()
        ext = {
            "URLs Only (TXT)": "txt",
            "URLs + Names (CSV)": "csv",
            "Full Details (JSON)": "json",
            "Full Details (CSV)": "csv",
            "Full Details (HTML)": "html",
        }.get(format_text, "txt")

        filter_str = {
            "txt": "Text Files (*.txt)",
            "csv": "CSV Files (*.csv)",
            "json": "JSON Files (*.json)",
            "html": "HTML Files (*.html)",
        }.get(ext, "All Files (*.*)")

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Export", self.path_edit.text(), filter_str
        )

        if file_path:
            self.path_edit.setText(file_path)
            self.export_btn.setEnabled(True)

    def _set_copy_mode(self):
        # فرمت Clipboard رو انتخاب کن
        for i in range(self.format_combo.count()):
            if "Clipboard" in self.format_combo.itemText(i):
                self.format_combo.setCurrentIndex(i)
                break

    def _center_on_parent(self):
        if self.parent():
            parent_geo = self.parent().geometry()
            self.move(
                parent_geo.x() + (parent_geo.width() - self.width()) // 2,
                parent_geo.y() + (parent_geo.height() - self.height()) // 2,
            )

    def get_data(self):
        return {
            "queue": self.selected_queue,
            "format": self.format_combo.currentText(),
            "path": self.path_edit.text(),
            "include_headers": self.header_cb.isChecked(),
        }
