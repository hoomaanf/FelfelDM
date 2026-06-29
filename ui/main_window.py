# =============================================================================
# ui/main_window.py
# =============================================================================
import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableView, QLineEdit, QLabel, QMessageBox, QHeaderView
)
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, QTimer

from ui.table_model import DownloadTableModel
from ui.dialogs import AddDownloadDialog
from ui.controllers import QueueController, DownloadController
from core.worker import BackendWorker
from core.data_store import DataStore
from core.local_server import LocalServer

logger = logging.getLogger(__name__)


class SearchProxyModel(QSortFilterProxyModel):
    """Proxy model for searching downloads by name or GID."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_text = ""

    def set_search_text(self, text: str) -> None:
        self._search_text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._search_text:
            return True
        model = self.sourceModel()
        if not model:
            return False
        # Search in name (column 0) and GID (column 5)
        for col in [0, 5]:
            index = model.index(source_row, col, source_parent)
            data = model.data(index, Qt.ItemDataRole.DisplayRole)
            if data and self._search_text in str(data).lower():
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self, worker: BackendWorker, store: DataStore, local_server: Optional[LocalServer] = None):
        super().__init__()
        self.worker = worker
        self.store = store
        self.local_server = local_server

        # Initialize controllers
        self.queue_controller = QueueController(store, self)
        self.download_controller = DownloadController(worker, self)

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

        # Connect signals - ensure GID is not None before emitting
        self.worker.download_added.connect(self._on_download_added)
        self.worker.download_removed.connect(self._on_download_removed)
        self.worker.stats_updated.connect(self.update_status)

        # Start worker after UI is fully loaded with error handling
        QTimer.singleShot(100, self._start_worker_safe)

    def _start_worker_safe(self) -> None:
        """Start the worker with exception handling."""
        try:
            self.worker.start()
        except Exception as e:
            logger.error("Failed to start worker: %s", e)
            QMessageBox.critical(self, "Error", f"Failed to start download engine: {e}")

    def _on_download_added(self, gid: str) -> None:
        if gid:
            logger.info(f"Download added: {gid}")

    def _on_download_removed(self, gid: str) -> None:
        if gid:
            logger.info(f"Download removed: {gid}")

    def create_toolbar(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        add_btn = QPushButton("➕ Add")
        add_btn.clicked.connect(self.add_download)
        layout.addWidget(add_btn)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_table)
        layout.addWidget(refresh_btn)

        layout.addStretch()

        layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter downloads...")
        self.search_edit.textChanged.connect(self.on_search_text_changed)
        layout.addWidget(self.search_edit)

        return widget

    def on_search_text_changed(self, text: str) -> None:
        self.proxy_model.set_search_text(text)

    def add_download(self) -> None:
        dialog = AddDownloadDialog(self)
        if dialog.exec() == AddDownloadDialog.DialogCode.Accepted:
            info = dialog.get_info()
            if info:
                gid = self.download_controller.add_download(info["url"], {"dir": info["path"]})
                if gid:
                    QMessageBox.information(self, "Added", f"Download added: {gid}")
                else:
                    QMessageBox.warning(self, "Error", "Failed to add download.")

    def refresh_table(self) -> None:
        self.model.refresh()

    def update_status(self, stats: dict) -> None:
        active = stats.get("numActive", 0)
        waiting = stats.get("numWaiting", 0)
        stopped = stats.get("numStopped", 0)
        self.status_label.setText(f"Active: {active}  Waiting: {waiting}  Stopped: {stopped}")

    def closeEvent(self, event) -> None:
        self.worker.stop()
        if self.local_server:
            self.local_server.stop()
        self.store.save()
        super().closeEvent(event)
