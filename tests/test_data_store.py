# tests/test_data_store.py
"""
Unit tests for DataStore class.
"""

import json
import pytest
import os
from unittest.mock import patch, MagicMock

from core.data_store import DataStore, Queue, KEYRING_SERVICE, KEYRING_KEY


class TestDataStore:
    """Test suite for DataStore class."""

    @pytest.fixture
    def store(self):
        """Create a DataStore instance with mocked file operations."""
        with patch('core.data_store.os.path.exists', return_value=False):
            with patch('core.data_store.os.makedirs'):
                store = DataStore()
                # Mock the save method to avoid actual file writes
                store.save = MagicMock()
                return store

    def test_init_creates_default_queue(self, store):
        """Test that default queue is created on init."""
        assert len(store.queues) >= 1
        default_q = store.get_queue("Default")
        assert default_q is not None
        assert default_q.name == "Default"

    def test_get_queue(self, store):
        """Test getting a queue by name."""
        q = store.get_queue("Default")
        assert q is not None
        assert q.name == "Default"

        non_existent = store.get_queue("NonExistent")
        assert non_existent is None

    def test_get_queue_index(self, store):
        """Test getting queue index by name."""
        idx = store.get_queue_index("Default")
        assert idx == 0

        idx = store.get_queue_index("NonExistent")
        assert idx is None

    @patch('core.data_store.keyring')
    def test_set_secret(self, mock_keyring, store):
        """Test setting secret and saving to keyring."""
        store.set_secret("my_secret")
        assert store.settings["aria2_secret"] == "my_secret"
        mock_keyring.set_password.assert_called_with(KEYRING_SERVICE, KEYRING_KEY, "my_secret")
        store.save.assert_called_once()

    @patch('core.data_store.keyring')
    def test_get_secret_from_keyring(self, mock_keyring, store):
        """Test loading secret from keyring."""
        mock_keyring.get_password.return_value = "keyring_secret"
        store._sync_secret_from_keyring()
        assert store.settings["aria2_secret"] == "keyring_secret"

    def test_queue_from_dict(self):
        """Test creating Queue from dictionary."""
        data = {
            "name": "TestQueue",
            "max_concurrent": 5,
            "save_path": "/tmp/downloads",
            "schedule_enabled": True,
            "schedule_start": "22:00",
            "schedule_end": "06:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "downloads": ["gid1", "gid2"],
            "paused": True,
        }
        q = Queue.from_dict(data)
        assert q.name == "TestQueue"
        assert q.max_concurrent == 5
        assert q.save_path == "/tmp/downloads"
        assert q.schedule_enabled is True
        assert len(q.downloads) == 2
        assert q.paused is True

    def test_queue_to_dict(self):
        """Test converting Queue to dictionary."""
        q = Queue("TestQueue", max_concurrent=5, save_path="/tmp/downloads", paused=False)
        q.downloads = ["gid1"]
        data = q.to_dict()
        assert data["name"] == "TestQueue"
        assert data["max_concurrent"] == 5
        assert data["paused"] is False
        assert "gid1" in data["downloads"]
