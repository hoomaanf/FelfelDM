# tests/test_helpers.py
"""
Unit tests for helper functions.
"""

import pytest
from utils.helpers import format_size, format_speed, get_category, check_disk_space


class TestHelpers:
    """Test suite for helper functions."""

    def test_format_size(self):
        """Test format_size function with various inputs."""
        assert format_size(0) == "0 B"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(1500) == "1.5 KB"
        assert format_size(1536) == "1.5 KB"
        assert format_size(1500000) == "1.4 MB"
        assert format_size(1024**3) == "1.0 GB"
        assert format_size(1024**4) == "1.0 TB"
        # Test negative values
        assert format_size(-100) == "0 B"
        # Test large values
        assert format_size(1024**5) == "1.0 PB"

    def test_format_speed(self):
        """Test format_speed function with various inputs."""
        assert format_speed(0) == "0 B/s"
        assert format_speed(1024) == "1.0 KB/s"
        assert format_speed(1024 * 1024) == "1.0 MB/s"
        assert format_speed(1500) == "1.5 KB/s"
        assert format_speed(1500000) == "1.4 MB/s"
        assert format_speed(1024**3) == "1.0 GB/s"
        assert format_speed(1024**4) == "1.0 TB/s"

    def test_get_category(self):
        """Test get_category function with various file extensions."""
        assert get_category("video.mp4") == "Video"
        assert get_category("music.mp3") == "Audio"
        assert get_category("archive.zip") == "Archive"
        assert get_category("document.pdf") == "Document"
        assert get_category("program.exe") == "Executable"
        assert get_category("file.torrent") == "Torrent"
        assert get_category("unknown.xyz") == "Other"
        assert get_category("file") == "Other"
        assert get_category("file.TXT") == "Document"  # Case insensitive

    @pytest.mark.skip(reason="Requires disk space check, may vary by environment")
    def test_check_disk_space(self):
        """Test check_disk_space function."""
        import tempfile
        import os

        # Test with existing path
        with tempfile.TemporaryDirectory() as tmpdir:
            result = check_disk_space(tmpdir, 1024)
            assert result is True or result is False  # Just check it returns bool

        # Test with invalid path should return True (graceful fallback)
        result = check_disk_space("/nonexistent/path", 1024)
        assert result is True

    @pytest.mark.parametrize("size,expected", [
        (0, "0 B"),
        (1023, "1023.0 B"),
        (1024, "1.0 KB"),
        (1048576, "1.0 MB"),
        (1073741824, "1.0 GB"),
        (1099511627776, "1.0 TB"),
    ])
    def test_format_size_parametrized(self, size, expected):
        """Parametrized test for format_size."""
        assert format_size(size) == expected
