"""Secure updater with checksum verification."""

import json
import logging
import hashlib
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from packaging.version import parse
import requests
from PyQt6.QtCore import QObject, pyqtSignal

logger: logging.Logger = logging.getLogger(__name__)


class Updater(QObject):
    update_available = pyqtSignal(str)
    update_downloaded = pyqtSignal(str)

    def __init__(self, current_version: str, update_url: str = "https://felfeldm.example.com/version.json") -> None:
        super().__init__()
        self.current_version = current_version
        self.update_url = update_url
        self._downloaded_file: Optional[Path] = None
        self._expected_checksum: Optional[str] = None

    def check_for_updates(self) -> Optional[str]:
        try:
            response = requests.get(self.update_url, timeout=10, verify=True)
            response.raise_for_status()
            data = response.json()

            latest_version = data.get("version")
            checksum = data.get("sha256")

            if not latest_version or not checksum:
                logger.error("Server response missing version or checksum")
                return None

            if parse(latest_version) > parse(self.current_version):
                self._expected_checksum = checksum
                logger.info("New version available: %s", latest_version)
                return latest_version
            return None

        except Exception as e:
            logger.error("Update check failed: %s", e)
            return None

    def download_update(self, new_version: str, download_url: str) -> bool:
        if not self._expected_checksum:
            logger.error("No checksum available")
            return False

        try:
            response = requests.get(download_url, stream=True, timeout=60, verify=True)
            response.raise_for_status()

            if os.name == "nt":
                suffix = ".exe.verified"
            elif sys.platform == "darwin":
                suffix = ".dmg.verified"
            else:
                suffix = ".bin.verified"

            fd, path = tempfile.mkstemp(suffix=suffix, prefix="felfeldm_update_")
            os.close(fd)
            path = Path(path)

            hasher = hashlib.sha256()
            total_size = 0

            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
                        total_size += len(chunk)

            computed_checksum = hasher.hexdigest()
            if computed_checksum != self._expected_checksum:
                logger.error("Checksum mismatch!")
                path.unlink()
                return False

            self._downloaded_file = path
            logger.info("Update verified: %s (%.2f MB)", path, total_size / (1024 * 1024))
            return True

        except Exception as e:
            logger.error("Download failed: %s", e)
            return False

    def install_update(self) -> bool:
        if not self._downloaded_file or not self._downloaded_file.exists():
            logger.error("No update file")
            return False

        try:
            installer_path = str(self._downloaded_file.absolute())

            if os.name == "nt":
                subprocess.Popen([installer_path, "/silent"], shell=False)
            elif sys.platform == "darwin":
                os.chmod(self._downloaded_file, 0o755)
                subprocess.Popen(["open", installer_path], shell=False)
            else:
                os.chmod(self._downloaded_file, 0o755)
                subprocess.Popen([installer_path], shell=False)

            logger.info("Update installer launched")
            return True

        except Exception as e:
            logger.error("Install failed: %s", e)
            return False

    def get_downloaded_file(self) -> Optional[Path]:
        return self._downloaded_file

    def clear_downloaded_file(self) -> None:
        if self._downloaded_file and self._downloaded_file.exists():
            try:
                self._downloaded_file.unlink()
            except Exception:
                pass
            self._downloaded_file = None
