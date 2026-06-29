# tests/test_websocket_client.py
"""
Unit tests for WebSocketClient class.
"""

import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from core.websocket_client import WebSocketClient


class TestWebSocketClient:
    """Test suite for WebSocketClient class."""

    @pytest.fixture
    def client(self, qtbot):
        """Create a WebSocketClient instance."""
        client = WebSocketClient(
            host="http://localhost",
            port=6800,
            secret="test_secret",
            cert_file=None,
            fingerprint=None,
        )
        # Use qtbot to handle Qt signals
        return client

    def test_init(self, client):
        """Test client initialization."""
        assert client.host == "http://localhost"
        assert client.port == 6800
        assert client.secret == "test_secret"
        assert client.cert_file is None
        assert client.fingerprint is None
        assert client._running is False
        assert client._connected is False

    def test_start_stop(self, client):
        """Test starting and stopping the client."""
        # Mock the WebSocketApp
        with patch('core.websocket_client.websocket.WebSocketApp') as mock_ws:
            mock_ws.return_value = MagicMock()
            client.start()
            assert client._running is True
            assert client._thread is not None

            # Allow some time for thread to start
            time.sleep(0.1)

            client.stop()
            assert client._running is False

    def test_start_already_running(self, client):
        """Test starting an already running client."""
        client._running = True
        client._thread = threading.Thread()
        client.start()  # Should return without creating new thread
        assert client._thread is not None

    def test_is_connected(self, client):
        """Test connection status."""
        assert client.is_connected() is False
        client._connected = True
        assert client.is_connected() is True

    @patch('core.websocket_client.websocket.WebSocketApp')
    def test_send_message_connected(self, mock_ws, client):
        """Test sending a message when connected."""
        mock_ws_instance = MagicMock()
        mock_ws.return_value = mock_ws_instance

        client._connected = True
        client._ws = mock_ws_instance

        message = {"test": "data"}
        client.send_message(message)

        # Verify the message was sent
        mock_ws_instance.send.assert_called_once_with(json.dumps(message))

    @patch('core.websocket_client.websocket.WebSocketApp')
    def test_send_message_not_connected(self, mock_ws, client):
        """Test sending a message when not connected."""
        client._connected = False
        client._ws = MagicMock()

        message = {"test": "data"}
        client.send_message(message)

        # Verify the message was not sent
        client._ws.send.assert_not_called()

    def test_on_open(self, client):
        """Test on_open callback."""
        assert client._connected is False
        assert client._reconnect_delay == 1.0

        mock_ws = MagicMock()
        client._on_open(mock_ws)

        assert client._connected is True
        assert client._reconnect_delay == 1.0

    def test_on_close(self, client):
        """Test on_close callback."""
        client._connected = True

        mock_ws = MagicMock()
        client._on_close(mock_ws, 1000, "Normal closure")

        assert client._connected is False

    @patch('core.websocket_client.ssl_utils.create_ssl_context')
    def test_run_with_ssl_failure(self, mock_create_ssl, client):
        """Test run with SSL failure - should raise RuntimeError."""
        client.host = "https://localhost"
        mock_create_ssl.side_effect = Exception("SSL error")

        client._running = True
        # The _run method should raise when SSL context creation fails
        with pytest.raises(RuntimeError):
            client._run()
