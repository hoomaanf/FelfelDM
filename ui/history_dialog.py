# ui/history_dialog.py
"""
Dialog to display download history with search and details.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QSortFilterProxyModel
from PyQt6.QtGui import QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QHeaderView, QLineEdit, QLabel,
    QMessageBox, QAbstractItemView,
)

from core.history import HistoryManager, DownloadHistory
from utils.helpers import format_size

logger = logging.getLogger(__name__)


class HistoryDialog(QDialog):
    """
    Dialog showing download history with search and filtering.
    """

    def __init__(self, history_manager: HistoryManager, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.history_manager = history_manager
        self.setWindowTitle("Download History")
        self.setMinimumSize(800, 500)
        self._setup_ui()
        self._load_history()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search by name, URL, or GID...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)

        # Table view
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name", "Size", "Status", "Start", "End", "Save Path"])
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.table.setModel(self.proxy_model)

        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._load_history)
        btn_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self._clear_history)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _load_history(self) -> None:
        """Load history into the table."""
        self.model.removeRows(0, self.model.rowCount())

        entries = self.history_manager.get_all()
        for entry in entries:
            row = [
                QStandardItem(entry.name),
                QStandardItem(format_size(entry.size)),
                QStandardItem(entry.status),
                QStandardItem(entry.start_time),
                QStandardItem(entry.end_time),
                QStandardItem(entry.save_path),
            ]
            # Store GID as user data in first column
            row[0].setData(entry.gid, Qt.ItemDataRole.UserRole)
            self.model.appendRow(row)

        # Set column widths
        for i in range(self.model.columnCount()):
            self.table.resizeColumnToContents(i)

    def _on_search_changed(self, text: str) -> None:
        """Filter history based on search text."""
        # Implement search via proxy model
        # For now, just reload with filter
        self._load_history()
        # Actually implement filter via proxy
        if text:
            # Use proxy model filter
            self.proxy_model.setFilterFixedString(text)
            self.proxy_model.setFilterKeyColumn(0)  # Name
        else:
            self.proxy_model.setFilterFixedString("")

    def _clear_history(self) -> None:
        """Clear all history after confirmation."""
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all download history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self._load_history()
            QMessageBox.information(self, "History Cleared", "All history entries have been deleted.")
