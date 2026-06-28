# tests/test_aria2_rpc.py
"""
Unit tests for aria2 RPC client.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from core.aria2_rpc import Aria2RPC


class TestAria2RPC:
    """Test suite for Aria2RPC class."""

    @pytest.fixture
    def rpc_client(self):
        """Create an RPC client instance for testing."""
        return Aria2RPC(
            host="http://localhost",
            port=6800,
            secret="test_secret",
            verify_ssl=False,
            timeout=5
        )

    @patch('core.aria2_rpc.requests.Session')
    def test_call_success(self, mock_session, rpc_client):
        """Test successful RPC call."""
        mock_response = Mock()
        mock_response.json.return_value = {"jsonrpc": "2.0", "id": "1", "result": "success"}
        mock_session.return_value.post.return_value = mock_response

        result = rpc_client._call("aria2.getGlobalStat")

        assert result == "success"
        mock_session.return_value.post.assert_called_once()

    @patch('core.aria2_rpc.requests.Session')
    def test_call_error(self, mock_session, rpc_client):
        """Test RPC call with error response."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "1",
            "error": {"code": -32601, "message": "Method not found"}
        }
        mock_session.return_value.post.return_value = mock_response

        result = rpc_client._call("aria2.invalidMethod")

        assert result is None

    @patch('core.aria2_rpc.requests.Session')
    def test_batch_call(self, mock_session, rpc_client):
        """Test batch RPC call using system.multicall."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": "1",
            "result": [
                {"result": "stat1"},
                {"result": "stat2"},
            ]
        }
        mock_session.return_value.post.return_value = mock_response

        calls = [
            {"method": "aria2.getGlobalStat"},
            {"method": "aria2.tellActive"},
        ]
        results = rpc_client.batch_call(calls)

        assert len(results) == 2
        assert results[0] == "stat1"
        assert results[1] == "stat2"

    def test_add_url(self, rpc_client):
        """Test adding a URL download."""
        with patch.object(rpc_client, '_call', return_value="gid123"):
            result = rpc_client.add_url("http://example.com/file.zip")
            assert result == "gid123"
            rpc_client._call.assert_called_with("aria2.addUri", ["http://example.com/file.zip"])

    def test_tell_status_with_fields(self, rpc_client):
        """Test tell_status with optional fields parameter."""
        with patch.object(rpc_client, '_call', return_value={"gid": "123", "status": "active"}):
            result = rpc_client.tell_status("123", ["gid", "status"])
            assert result is not None
            assert result.get("gid") == "123"
            rpc_client._call.assert_called_with("aria2.tellStatus", ["123", ["gid", "status"]])

    def test_tell_status_without_fields(self, rpc_client):
        """Test tell_status without fields parameter."""
        with patch.object(rpc_client, '_call', return_value={"gid": "123"}):
            result = rpc_client.tell_status("123")
            assert result is not None
            rpc_client._call.assert_called_with("aria2.tellStatus", ["123"])

    def test_set_secret(self, rpc_client):
        """Test updating the RPC secret."""
        rpc_client.set_secret("new_secret")
        assert rpc_client.secret == "new_secret"

    def test_ensure_session(self, rpc_client):
        """Test session recreation."""
        old_session = rpc_client._session
        rpc_client._ensure_session()
        assert rpc_client._session is not old_session
        assert rpc_client._session.verify == old_session.verify
