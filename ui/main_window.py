# =============================================================================
# ui/main_window.py
# =============================================================================
import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QToolBar, QLineEdit, QLabel, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex

from ui.table_model import DownloadTableModel
from ui.dialogs import AddDownloadDialog
from core.worker import BackendWorker
from core.data_store import DataStore
from core.queue_model import Queue
from core.local_server import LocalServer

logger = logging.getLogger(__name__)


class SearchProxyModel(QSortFilterProxyModel):
    """Proxy model for searching downloads by name (column 0)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""

    def set_search_text(self, text: str):
        self._search_text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._search_text:
            return True
        model = self.sourceModel()
        if not model:
            return False
        # Search in column 0 (Name)
        index = model.index(source_row, 0, source_parent)
        name = model.data(index, Qt.ItemDataRole.DisplayRole)
        if name and self._search_text in str(name).lower():
            return True
        return False


class MainWindow(QMainWindow):
    def __init__(self, worker: BackendWorker, store: DataStore, local_server: Optional[LocalServer] = None):
        super().__init__()
        self.worker = worker
        self.store = store
        self.local_server = local_server
        self.setWindowTitle("FelfelDM")

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Toolbar with search
        toolbar = self.create_toolbar()
        layout.addWidget(toolbar)

        # Table view
        self.model = DownloadTableModel(worker)
        self.proxy_model = SearchProxyModel()
        self.proxy_model.setSourceModel(self.model)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel("Ready")
        self.statusBar().addWidget(self.status_label)

        # Connect signals
        self.worker.stats_updated.connect(self.update_status)

        # Start worker
        self.worker.start()

    def create_toolbar(self) -> QWidget:
        """Create toolbar with add button and search box."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add download button
        add_btn = QPushButton("➕ Add")
        add_btn.clicked.connect(self.add_download)
        layout.addWidget(add_btn)

        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_table)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        # Search box
        layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter downloads...")
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        layout.addWidget(self.search_edit)

        return widget

    def on_search_text_changed(self, text: str):
        """Update search filter."""
        self.proxy_model.set_search_text(text)

    def add_download(self):
        """Open Add Download dialog."""
        dialog = AddDownloadDialog(self)
        if dialog.exec() == AddDownloadDialog.DialogCode.Accepted:
            info = dialog.get_info()
            if info:
                # Add download via worker
                # In a full implementation, we would call aria2.addUri or addMagnet
                # For now, we just show a message
                QMessageBox.information(self, "Added", f"Added: {info['url']}")

    def refresh_table(self):
        """Manually refresh table data."""
        self.model.refresh()

    def update_status(self, stats: dict):
        """Update status bar with global stats."""
        active = stats.get("numActive", 0)
        waiting = stats.get("numWaiting", 0)
        stopped = stats.get("numStopped", 0)
        self.status_label.setText(f"Active: {active}  Waiting: {waiting}  Stopped: {stopped}")

    def closeEvent(self, event):
        """Clean up resources on close."""
        self.worker.stop()
        if self.local_server:
            self.local_server.stop()
        self.store.save()
        super().closeEvent(event)
