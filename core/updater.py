"""
Automatic updater: checks for new versions and installs updates.
"""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from packaging.version import Version, parse

import requests
from PyQt6.QtCore import QObject, pyqtSignal

logger: logging.Logger = logging.getLogger(__name__)


class Updater(QObject):
    """
    Checks for updates and installs them.
    """

    update_available = pyqtSignal(str)  # new version string
    update_downloaded = pyqtSignal(str)  # path to downloaded installer

    def __init__(self, current_version: str, update_url: str = "https://felfeldm.example.com/version.json") -> None:
        super().__init__()
        self.current_version = current_version
        self.update_url = update_url
        self._downloaded_file: Optional[Path] = None

    def check_for_updates(self) -> Optional[str]:
        """Check server for newer version. Returns new version string if available, else None."""
        try:
            response = requests.get(self.update_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            latest_version = data.get("version")
            if latest_version:
                if parse(latest_version) > parse(self.current_version):
                    logger.info("New version available: %s", latest_version)
                    return latest_version
                else:
                    logger.info("Already on latest version.")
            return None
        except Exception as e:
            logger.error("Update check failed: %s", e)
            return None

    def download_update(self, new_version: str, download_url: str) -> bool:
        """Download the update installer."""
        try:
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()
            # Save to temp file
            fd, path = tempfile.mkstemp(suffix=".exe" if os.name == "nt" else ".bin", prefix="felfeldm_update_")
            os.close(fd)
            path = Path(path)
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            self._downloaded_file = path
            logger.info("Update downloaded to %s", path)
            return True
        except Exception as e:
            logger.error("Failed to download update: %s", e)
            return False

    def install_update(self) -> bool:
        """Install the downloaded update by running the installer."""
        if not self._downloaded_file or not self._downloaded_file.exists():
            logger.error("No update file to install.")
            return False
        try:
            # Platform-specific installation without shell=True
            if os.name == "nt":
                subprocess.Popen([str(self._downloaded_file), "/silent"])
            else:
                # For Linux/macOS, make executable and run
                os.chmod(self._downloaded_file, 0o755)
                subprocess.Popen([str(self._downloaded_file)])
            logger.info("Update installer launched. Exiting application.")
            return True
        except Exception as e:
            logger.error("Failed to install update: %s", e)
            return False
