# ui/log_viewer.py

import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QCheckBox,
    QLabel,
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QFont, QTextCursor

from utils.logger import get_log_file_path
from utils.helpers import get_icon


class LogViewerDialog(QDialog):
    """Live view of the application log file."""

    MAX_LINES = 2000  # only keep the last N lines in the widget

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FelfelDM — Logs")
        self.setMinimumSize(800, 500)

        self._log_path = get_log_file_path()
        self._last_size = 0

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # ── Top row: info + controls ──
        top_row = QHBoxLayout()

        self.path_label = QLabel(f"📄 {self._log_path}")
        self.path_label.setStyleSheet("color: #888; font-size: 11px;")
        self.path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        top_row.addWidget(self.path_label, 1)

        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        top_row.addWidget(self.autoscroll_cb)

        self.live_cb = QCheckBox("Live")
        self.live_cb.setChecked(True)
        top_row.addWidget(self.live_cb)

        main_layout.addLayout(top_row)

        # ── Text area ──
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(9)
        self.text.setFont(font)
        self.text.setStyleSheet("""
            QPlainTextEdit {
                background: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        main_layout.addWidget(self.text, 1)

        # ── Bottom buttons ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        clear_btn = QPushButton(get_icon("edit-clear"), "Clear Log File")
        clear_btn.clicked.connect(self._clear_log)
        btn_row.addWidget(clear_btn)

        refresh_btn = QPushButton(get_icon("view-refresh"), "Refresh")
        refresh_btn.clicked.connect(self._reload_all)
        btn_row.addWidget(refresh_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        main_layout.addLayout(btn_row)

        # ── Initial load ──
        self._reload_all()

        # ── Live refresh timer ──
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ── Helpers ────────────────────────────────────────────

    def _reload_all(self):
        """Read the whole log file and show it."""
        if not self._log_path.exists():
            self.text.setPlainText("(log file is empty)")
            self._last_size = 0
            return

        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._last_size = self._log_path.stat().st_size
        except OSError as e:
            self.text.setPlainText(f"(could not read log: {e})")
            return

        self.text.setPlainText(content)
        self._trim_if_needed()
        if self.autoscroll_cb.isChecked():
            self._scroll_to_bottom()

    def _tick(self):
        """Called every 500ms. Append new lines if the file grew."""
        if not self.live_cb.isChecked():
            return
        if not self._log_path.exists():
            return

        try:
            size = self._log_path.stat().st_size
        except OSError:
            return

        if size == self._last_size:
            return

        # File rotated or truncated?
        if size < self._last_size:
            self._reload_all()
            return

        # Read new bytes from the last position
        try:
            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_size)
                new_content = f.read()
            self._last_size = size
        except OSError:
            return

        if not new_content:
            return

        cursor = self.text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(new_content)
        self.text.setTextCursor(cursor)

        self._trim_if_needed()
        if self.autoscroll_cb.isChecked():
            self._scroll_to_bottom()

    def _trim_if_needed(self):
        """Keep the widget from growing forever."""
        doc = self.text.document()
        if doc.blockCount() > self.MAX_LINES:
            cursor = self.text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.KeepAnchor,
                doc.blockCount() - self.MAX_LINES,
            )
            cursor.removeSelectedText()

    def _scroll_to_bottom(self):
        sb = self.text.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_log(self):
        try:
            if self._log_path.exists():
                self._log_path.write_text("", encoding="utf-8")
        except OSError:
            pass
        self._last_size = 0
        self.text.setPlainText("")

    def closeEvent(self, event):
        if hasattr(self, "_timer") and self._timer:
            self._timer.stop()
        event.accept()