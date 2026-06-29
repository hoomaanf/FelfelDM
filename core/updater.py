# core/updater.py
"""
Automatic updater: checks for new versions and installs updates.
Includes SHA-256 checksum verification for security.
"""

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from packaging.version import parse
from PyQt6.QtCore import QObject, pyqtSignal

logger: logging.Logger = logging.getLogger(__name__)


class Updater(QObject):
    """
    Checks for updates and installs them with integrity verification.
    """

    update_available = pyqtSignal(str)  # new version string
    update_downloaded = pyqtSignal(str)  # path to downloaded installer
    update_verified = pyqtSignal(bool)   # checksum verification result

    def __init__(
        self,
        current_version: str,
        update_url: str = "https://api.github.com/repos/hoomaanf/FelfelDM/releases/latest",
    ) -> None:
        super().__init__()
        self.current_version = current_version
        self.update_url = update_url
        self._downloaded_file: Optional[Path] = None
        self._expected_checksum: Optional[str] = None

    def check_for_updates(self) -> Optional[str]:
        """
        Check server for newer version.
        Returns new version string if available, else None.
        """
        try:
            response = requests.get(self.update_url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Support both custom version.json and GitHub API format
            if "version" in data:
                latest_version = data.get("version")
                self._expected_checksum = data.get("checksum")
            elif "tag_name" in data:
                latest_version = data.get("tag_name", "").lstrip("v")
                # GitHub releases: look for assets with checksum
                assets = data.get("assets", [])
                for asset in assets:
                    if asset.get("name", "").endswith(".sha256"):
                        try:
                            checksum_response = requests.get(asset.get("browser_download_url"), timeout=10)
                            checksum_response.raise_for_status()
                            self._expected_checksum = checksum_response.text.strip().split()[0]
                        except Exception as e:
                            logger.warning("Failed to fetch checksum: %s", e)
            else:
                logger.error("Invalid update metadata format")
                return None

            if latest_version and parse(latest_version) > parse(self.current_version):
                logger.info("New version available: %s", latest_version)
                return latest_version
            else:
                logger.info("Already on latest version.")
                return None

        except Exception as e:
            logger.error("Update check failed: %s", e)
            return None

    def download_update(self, new_version: str, download_url: str) -> bool:
        """
        Download the update installer and verify its integrity.
        """
        try:
            response = requests.get(download_url, stream=True, timeout=60)
            response.raise_for_status()

            # Save to temp file
            fd, path = tempfile.mkstemp(
                suffix=".exe" if os.name == "nt" else ".bin",
                prefix="felfeldm_update_"
            )
            os.close(fd)
            path = Path(path)

            # Download with hash calculation
            sha256_hash = hashlib.sha256()
            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        sha256_hash.update(chunk)

            self._downloaded_file = path
            logger.info("Update downloaded to %s", path)

            # Verify checksum if available
            if self._expected_checksum:
                computed_checksum = sha256_hash.hexdigest()
                if computed_checksum.lower() != self._expected_checksum.lower():
                    logger.error(
                        "Checksum verification failed! Expected: %s, Got: %s",
                        self._expected_checksum,
                        computed_checksum
                    )
                    # Clean up the invalid file
                    try:
                        path.unlink()
                    except Exception:
                        pass
                    self.update_verified.emit(False)
                    return False
                else:
                    logger.info("Checksum verification passed")
                    self.update_verified.emit(True)
            else:
                logger.warning("No checksum provided for update, skipping verification")
                self.update_verified.emit(False)

            return True

        except Exception as e:
            logger.error("Failed to download update: %s", e)
            return False

    def install_update(self) -> bool:
        """
        Install the downloaded update by running the installer.
        """
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

    def get_downloaded_file(self) -> Optional[Path]:
        return self._downloaded_file
