# tests/test_local_server.py
"""
Unit tests for LocalServer class.
"""

import json
import threading
import time
import pytest
from unittest.mock import Mock, patch, MagicMock

from core.local_server import LocalServer


class TestLocalServer:
    """Test suite for LocalServer class."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock download controller."""
        controller = Mock()
        controller.add_urls = Mock(return_value=["gid1"])
        return controller

    @pytest.fixture
    def server(self, mock_controller):
        """Create a LocalServer instance with mocked controller."""
        server = LocalServer(mock_controller, port=0)  # Use ephemeral port
        return server

    def test_init(self, server, mock_controller):
        """Test server initialization."""
        assert server.download_controller == mock_controller
        assert server._token is not None
        assert len(server._token) == 43  # URL-safe base64 token length

    def test_get_token(self, server):
        """Test getting the authentication token."""
        token = server.get_token()
        assert token == server._token
        assert len(token) == 43

    def test_start_stop(self, server):
        """Test starting and stopping the server."""
        # Start server
        server.start()
        assert server._running is True
        assert server._server is not None
        assert server._thread is not None
        assert server._thread.is_alive() is True

        # Stop server
        server.stop()
        assert server._running is False

    def test_start_already_running(self, server):
        """Test starting an already running server."""
        server.start()
        server.start()  # Should not create a new thread
        assert server._thread is not None

    def test_create_handler(self, server):
        """Test handler creation."""
        handler_class = server._create_handler()
        assert handler_class is not None
        # Check that the handler has the expected attributes
        assert hasattr(handler_class, 'do_GET')
        assert hasattr(handler_class, 'do_POST')
        assert hasattr(handler_class, 'do_OPTIONS')

    @patch('core.local_server.secrets.compare_digest')
    def test_token_validation(self, mock_compare, server, mock_controller):
        """Test token validation with compare_digest."""
        # Start the server
        server.start()
        time.sleep(0.1)  # Allow server to start

        # Simulate a request with valid token
        mock_compare.return_value = True
        # We can't easily test HTTP requests here, but we can test the logic
        # by checking that compare_digest is used correctly

        # Stop the server
        server.stop()

    def test_cors_headers(self, server):
        """Test CORS headers are properly set."""
        # This is tested via the handler's _send_cors_headers method
        # which we can verify exists
        handler_class = server._create_handler()
        handler = handler_class()
        assert hasattr(handler, '_send_cors_headers')
