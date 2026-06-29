# tests/test_main_window.py
"""
Unit tests for MainWindow class.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow, QueueController, DownloadController, TrayController


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for testing."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestMainWindow:
    """Test suite for MainWindow class."""

    @patch('ui.main_window.DataStore')
    @patch('ui.main_window.Aria2Manager')
    @patch('ui.main_window.Aria2RPC')
    @patch('ui.main_window.BackendWorker')
    @patch('ui.main_window.LocalServer')
    def test_init(self, mock_local_server, mock_worker, mock_rpc,
                  mock_manager, mock_store, qapp):
        """Test MainWindow initialization."""
        # Mock dependencies
        mock_store_instance = Mock()
        mock_store_instance.queues = []
        mock_store_instance.settings = {"aria2_host": "localhost", "aria2_port": 6800}
        mock_store.return_value = mock_store_instance

        mock_manager_instance = Mock()
        mock_manager.return_value = mock_manager_instance

        mock_rpc_instance = Mock()
        mock_rpc.return_value = mock_rpc_instance

        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance

        mock_local_server_instance = Mock()
        mock_local_server.return_value = mock_local_server_instance

        window = MainWindow()
        assert window is not None
        assert hasattr(window, 'store')
        assert hasattr(window, 'aria2_manager')
        assert hasattr(window, 'aria2')
        assert hasattr(window, 'download_controller')
        assert hasattr(window, 'queue_controller')
        assert hasattr(window, 'tray_controller')
        assert hasattr(window, 'worker')
        assert hasattr(window, 'local_server')

    @patch('ui.main_window.DataStore')
    @patch('ui.main_window.Aria2Manager')
    @patch('ui.main_window.Aria2RPC')
    @patch('ui.main_window.BackendWorker')
    @patch('ui.main_window.LocalServer')
    def test_update_queue_ui(self, mock_local_server, mock_worker, mock_rpc,
                              mock_manager, mock_store, qapp):
        """Test updating queue UI."""
        mock_store_instance = Mock()
        mock_store_instance.queues = []
        mock_store_instance.settings = {"aria2_host": "localhost", "aria2_port": 6800}
        mock_store.return_value = mock_store_instance

        mock_manager_instance = Mock()
        mock_manager.return_value = mock_manager_instance

        mock_rpc_instance = Mock()
        mock_rpc.return_value = mock_rpc_instance

        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance

        mock_local_server_instance = Mock()
        mock_local_server.return_value = mock_local_server_instance

        window = MainWindow()
        window._update_queue_ui()
        # Verify that the queue combo was updated
        assert window.queue_combo is not None

    @patch('ui.main_window.DataStore')
    @patch('ui.main_window.Aria2Manager')
    @patch('ui.main_window.Aria2RPC')
    @patch('ui.main_window.BackendWorker')
    @patch('ui.main_window.LocalServer')
    def test_apply_theme_from_settings(self, mock_local_server, mock_worker, mock_rpc,
                                        mock_manager, mock_store, qapp):
        """Test applying theme from settings."""
        mock_store_instance = Mock()
        mock_store_instance.queues = []
        mock_store_instance.settings = {"aria2_host": "localhost", "aria2_port": 6800, "theme": "dark"}
        mock_store.return_value = mock_store_instance

        mock_manager_instance = Mock()
        mock_manager.return_value = mock_manager_instance

        mock_rpc_instance = Mock()
        mock_rpc.return_value = mock_rpc_instance

        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance

        mock_local_server_instance = Mock()
        mock_local_server.return_value = mock_local_server_instance

        with patch('ui.main_window.apply_theme') as mock_apply_theme:
            with patch('ui.main_window.detect_theme') as mock_detect_theme:
                mock_detect_theme.return_value = True
                window = MainWindow()
                window._apply_theme_from_settings()
                mock_apply_theme.assert_called()

    @patch('ui.main_window.DataStore')
    @patch('ui.main_window.Aria2Manager')
    @patch('ui.main_window.Aria2RPC')
    @patch('ui.main_window.BackendWorker')
    @patch('ui.main_window.LocalServer')
    @patch('ui.main_window.QMessageBox')
    def test_on_connection_changed(self, mock_msgbox, mock_local_server, mock_worker,
                                    mock_rpc, mock_manager, mock_store, qapp):
        """Test connection status change handling."""
        mock_store_instance = Mock()
        mock_store_instance.queues = []
        mock_store_instance.settings = {"aria2_host": "localhost", "aria2_port": 6800}
        mock_store.return_value = mock_store_instance

        mock_manager_instance = Mock()
        mock_manager.return_value = mock_manager_instance

        mock_rpc_instance = Mock()
        mock_rpc.return_value = mock_rpc_instance

        mock_worker_instance = Mock()
        mock_worker.return_value = mock_worker_instance

        mock_local_server_instance = Mock()
        mock_local_server.return_value = mock_local_server_instance

        window = MainWindow()
        window._on_connection_changed(True)
        assert window.connection_indicator is not None
        assert window.status_label.text() == "Connected to aria2"

        window._on_connection_changed(False)
        assert window.status_label.text() == "Disconnected from aria2"


class TestQueueController:
    """Test suite for QueueController class."""

    @patch('ui.main_window.DataStore')
    def test_get_queues(self, mock_store):
        """Test getting queues."""
        mock_store_instance = Mock()
        mock_store_instance.queues = [Mock(name="Queue1"), Mock(name="Queue2")]
        mock_store.return_value = mock_store_instance

        controller = QueueController(mock_store_instance)
        queues = controller.get_queues()
        assert len(queues) == 2

    @patch('ui.main_window.DataStore')
    def test_get_current_queue(self, mock_store):
        """Test getting current queue."""
        mock_store_instance = Mock()
        mock_queue = Mock(name="CurrentQueue")
        mock_store_instance.queues = [mock_queue, Mock(name="Queue2")]
        mock_store.return_value = mock_store_instance

        controller = QueueController(mock_store_instance)
        controller.current_index = 0
        queue = controller.get_current_queue()
        assert queue == mock_queue

    @patch('ui.main_window.DataStore')
    def test_set_current_index(self, mock_store):
        """Test setting current index."""
        mock_store_instance = Mock()
        mock_store_instance.queues = [Mock(name="Queue1"), Mock(name="Queue2")]
        mock_store.return_value = mock_store_instance

        controller = QueueController(mock_store_instance)
        controller.set_current_index(1)
        assert controller.current_index == 1
        controller.queue_changed.emit()


class TestDownloadController:
    """Test suite for DownloadController class."""

    @patch('ui.main_window.DataStore')
    def test_add_urls(self, mock_store):
        """Test adding URLs."""
        mock_store_instance = Mock()
        mock_store_instance.queues = [Mock(name="Queue1")]
        mock_store.return_value = mock_store_instance

        mock_aria2 = Mock()
        mock_aria2.add_url.return_value = "gid123"

        controller = DownloadController(mock_aria2, mock_store_instance)
        urls = ["http://example.com/file1.zip", "http://example.com/file2.zip"]
        gids = controller.add_urls(urls, 0, {})

        assert len(gids) == 2
        assert gids[0] == "gid123"
        assert gids[1] == "gid123"
        assert len(mock_store_instance.queues[0].downloads) == 2

    @patch('ui.main_window.DataStore')
    def test_pause(self, mock_store):
        """Test pausing a download."""
        mock_store_instance = Mock()
        mock_aria2 = Mock()
        mock_aria2.pause.return_value = {"gid": "gid123"}

        controller = DownloadController(mock_aria2, mock_store_instance)
        controller.pause("gid123")
        mock_aria2.pause.assert_called_with("gid123")

    @patch('ui.main_window.DataStore')
    def test_remove(self, mock_store):
        """Test removing a download."""
        mock_store_instance = Mock()
        mock_aria2 = Mock()

        controller = DownloadController(mock_aria2, mock_store_instance)
        controller.remove("gid123")
        mock_aria2.remove.assert_called_with("gid123")
        assert "gid123" in controller._cleared_gids


class TestTrayController:
    """Test suite for TrayController class."""

    @patch('ui.main_window.QSystemTrayIcon')
    def test_init(self, mock_tray, qapp):
        """Test TrayController initialization."""
        controller = TrayController()
        assert controller.tray is not None
        mock_tray.assert_called_once()

    @patch('ui.main_window.QSystemTrayIcon')
    def test_show_message(self, mock_tray, qapp):
        """Test showing a tray message."""
        mock_tray_instance = Mock()
        mock_tray.return_value = mock_tray_instance

        controller = TrayController()
        controller.show_message("Title", "Message")
        mock_tray_instance.showMessage.assert_called_with("Title", "Message",
                                                          mock_tray_instance.MessageIcon.Information)

    @patch('ui.main_window.QSystemTrayIcon')
    def test_set_icon(self, mock_tray, qapp):
        """Test setting tray icon."""
        mock_tray_instance = Mock()
        mock_tray.return_value = mock_tray_instance

        mock_icon = Mock()
        controller = TrayController()
        controller.set_icon(mock_icon)
        mock_tray_instance.setIcon.assert_called_with(mock_icon)
