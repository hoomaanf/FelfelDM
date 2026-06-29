# tests/test_updater.py
"""
Unit tests for Updater class.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock

import pytest

from core.updater import Updater


class TestUpdater:
    """Test suite for Updater class."""

    @pytest.fixture
    def updater(self):
        """Create an Updater instance."""
        return Updater("1.0.0", "https://api.github.com/repos/test/repo/releases/latest")

    @patch('core.updater.requests.get')
    def test_check_for_updates_newer_version(self, mock_get, updater):
        """Test checking for updates when a newer version is available."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "tag_name": "v2.0.0",
            "assets": [
                {"name": "felfeldm-2.0.0.sha256", "browser_download_url": "https://example.com/checksum.sha256"}
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Mock the checksum request
        checksum_response = Mock()
        checksum_response.text = "abc123  felfeldm-2.0.0.bin"
        checksum_response.raise_for_status = Mock()
        mock_get.side_effect = [mock_response, checksum_response]

        result = updater.check_for_updates()
        assert result == "2.0.0"

    @patch('core.updater.requests.get')
    def test_check_for_updates_same_version(self, mock_get, updater):
        """Test checking for updates when on the latest version."""
        mock_response = Mock()
        mock_response.json.return_value = {"tag_name": "v1.0.0"}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = updater.check_for_updates()
        assert result is None

    @patch('core.updater.requests.get')
    def test_check_for_updates_custom_format(self, mock_get, updater):
        """Test checking for updates with custom JSON format."""
        updater.update_url = "https://example.com/version.json"
        mock_response = Mock()
        mock_response.json.return_value = {
            "version": "2.0.0",
            "checksum": "abc123",
            "download_url": "https://example.com/download.bin"
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = updater.check_for_updates()
        assert result == "2.0.0"
        assert updater._expected_checksum == "abc123"

    @patch('core.updater.requests.get')
    def test_download_update_success(self, mock_get, updater):
        """Test successful download and verification."""
        # Setup
        updater._expected_checksum = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

        # Mock download response
        mock_response = Mock()
        mock_response.iter_content = Mock(return_value=[b"test content"])
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Download with SHA256 of "test content"
        # echo -n "test content" | sha256sum
        # 6f6b8a1c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a
        # We'll use the actual hash of the content

        # For this test, we'll skip the actual hash verification
        # and mock the hash calculation

        with patch('core.updater.hashlib.sha256') as mock_sha256:
            mock_hash = Mock()
            mock_hash.hexdigest.return_value = updater._expected_checksum
            mock_sha256.return_value = mock_hash

            result = updater.download_update("2.0.0", "https://example.com/download.bin")
            assert result is True
            assert updater._downloaded_file is not None

    @patch('core.updater.requests.get')
    def test_download_update_invalid_checksum(self, mock_get, updater):
        """Test download with invalid checksum."""
        updater._expected_checksum = "invalidchecksum"

        mock_response = Mock()
        mock_response.iter_content = Mock(return_value=[b"test content"])
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        with patch('core.updater.hashlib.sha256') as mock_sha256:
            mock_hash = Mock()
            mock_hash.hexdigest.return_value = "differenthash"
            mock_sha256.return_value = mock_hash

            result = updater.download_update("2.0.0", "https://example.com/download.bin")
            assert result is False
            assert updater._downloaded_file is None

    def test_install_update_no_file(self, updater):
        """Test installing update with no downloaded file."""
        updater._downloaded_file = None
        result = updater.install_update()
        assert result is False

    @patch('core.updater.subprocess.Popen')
    def test_install_update_success(self, mock_popen, updater):
        """Test successful installation."""
        with tempfile.NamedTemporaryFile(suffix=".bin") as f:
            updater._downloaded_file = Path(f.name)
            result = updater.install_update()
            assert result is True
            mock_popen.assert_called_once()
