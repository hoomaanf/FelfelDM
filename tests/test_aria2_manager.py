# tests/test_aria2_manager.py
"""
Unit tests for Aria2Manager class.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

from core.aria2_manager import Aria2Manager, CertificateManager


class TestCertificateManager:
    """Test suite for CertificateManager class."""

    @patch('core.aria2_manager.CertificateManager._ensure_dirs')
    def test_init(self, mock_ensure_dirs):
        """Test certificate manager initialization."""
        cm = CertificateManager()
        assert cm._fingerprint is None
        assert cm._cert_generated is False
        assert cm._custom_cert_used is False
        mock_ensure_dirs.assert_called_once()

    @patch('core.aria2_manager.CertificateManager._ensure_dirs')
    def test_is_self_signed(self, mock_ensure_dirs):
        """Test is_self_signed property."""
        cm = CertificateManager()
        cm._cert_generated = True
        cm._custom_cert_used = False
        assert cm.is_self_signed() is True

        cm._custom_cert_used = True
        assert cm.is_self_signed() is False

    @patch('core.aria2_manager.shutil.copy2')
    @patch('core.aria2_manager.get_fingerprint_from_cert')
    @patch('core.aria2_manager.CertificateManager._ensure_dirs')
    def test_set_custom_certificate_success(self, mock_ensure_dirs, mock_get_fingerprint, mock_copy2):
        """Test setting a custom certificate successfully."""
        cm = CertificateManager()
        cert_path = Path("/path/to/cert.crt")
        key_path = Path("/path/to/key.key")

        # Mock file existence
        cert_path.exists = Mock(return_value=True)
        key_path.exists = Mock(return_value=True)

        mock_get_fingerprint.return_value = "abc123"

        result = cm.set_custom_certificate(cert_path, key_path)
        assert result is True
        assert cm._fingerprint == "abc123"
        assert cm._cert_generated is True
        assert cm._custom_cert_used is True
        mock_copy2.assert_has_calls([call(cert_path, cm.CERT_FILE), call(key_path, cm.KEY_FILE)])

    @patch('core.aria2_manager.CertificateManager._ensure_dirs')
    def test_set_custom_certificate_file_not_found(self, mock_ensure_dirs):
        """Test setting custom certificate when files don't exist."""
        cm = CertificateManager()
        cert_path = Path("/path/to/cert.crt")
        key_path = Path("/path/to/key.key")

        cert_path.exists = Mock(return_value=False)
        key_path.exists = Mock(return_value=True)

        result = cm.set_custom_certificate(cert_path, key_path)
        assert result is False

    @patch('core.aria2_manager.subprocess.Popen')
    @patch('core.aria2_manager.CertificateManager.generate_certificates')
    @patch('core.aria2_manager.CertificateManager.is_self_signed')
    @patch('core.aria2_manager.Aria2Manager._generate_secret')
    def test_aria2_manager_start_success(self, mock_secret, mock_is_self_signed,
                                          mock_generate_certs, mock_popen):
        """Test starting aria2 successfully."""
        mock_secret.return_value = "test_secret"
        mock_is_self_signed.return_value = False
        mock_generate_certs.return_value = True

        manager = Aria2Manager()
        mock_popen.return_value = Mock()

        with patch('time.sleep', return_value=None):
            result = manager.start()

        assert result is True
        assert manager._started is True
        mock_popen.assert_called_once()

    @patch('core.aria2_manager.subprocess.Popen')
    @patch('core.aria2_manager.CertificateManager.generate_certificates')
    @patch('core.aria2_manager.Aria2Manager._generate_secret')
    def test_aria2_manager_start_file_not_found(self, mock_secret, mock_generate_certs, mock_popen):
        """Test starting aria2 when binary not found."""
        mock_secret.return_value = "test_secret"
        mock_generate_certs.return_value = True
        mock_popen.side_effect = FileNotFoundError()

        manager = Aria2Manager()
        result = manager.start()

        assert result is False
        assert manager._started is False

    @patch('core.aria2_manager.subprocess.Popen')
    @patch('core.aria2_manager.CertificateManager.generate_certificates')
    @patch('core.aria2_manager.Aria2Manager._generate_secret')
    def test_aria2_manager_stop(self, mock_secret, mock_generate_certs, mock_popen):
        """Test stopping aria2."""
        mock_secret.return_value = "test_secret"
        mock_generate_certs.return_value = True

        mock_process = Mock()
        mock_popen.return_value = mock_process

        manager = Aria2Manager()
        with patch('time.sleep', return_value=None):
            manager.start()

        manager.stop()
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once_with(timeout=5)
        assert manager._started is False

    @patch('core.aria2_manager.Aria2Manager.stop')
    @patch('core.aria2_manager.Aria2Manager.start')
    def test_restart(self, mock_start, mock_stop):
        """Test restarting aria2."""
        mock_start.return_value = True
        manager = Aria2Manager()

        result = manager.restart()
        mock_stop.assert_called_once()
        mock_start.assert_called_once()
        assert result is True
