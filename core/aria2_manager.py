# =============================================================================
# core/aria2_manager.py
# =============================================================================
import os
import subprocess
import logging
from pathlib import Path
from typing import Optional

from core.constants import ARIA2_CONFIG_DIR, ARIA2_SECRET_FILE

logger = logging.getLogger(__name__)


def _save_secret_to_file(secret: str) -> None:
    """Save aria2 secret to a file with restricted permissions (atomic creation)."""
    try:
        ARIA2_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Try to create the file exclusively with mode 0o600
        fd = os.open(
            ARIA2_SECRET_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TRUNC,
            0o600
        )
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(secret)
    except FileExistsError:
        # File exists, write with restricted mode
        with open(ARIA2_SECRET_FILE, 'w', encoding='utf-8') as f:
            f.write(secret)
        os.chmod(ARIA2_SECRET_FILE, 0o600)
    except OSError as e:
        logger.error("Failed to save secret to file: %s", e)
        raise


def _get_secret_from_file() -> Optional[str]:
    """Read secret from file, validating content."""
    if not ARIA2_SECRET_FILE.exists():
        return None
    try:
        with open(ARIA2_SECRET_FILE, 'r', encoding='utf-8') as f:
            secret = f.read().strip()
        if not secret or len(secret) < 8:
            logger.warning("Secret file contains invalid secret")
            return None
        return secret
    except (OSError, UnicodeDecodeError) as e:
        logger.error("Failed to read secret from file: %s", e)
        return None


def start_aria2(secret: str, rpc_port: int = 6800, download_dir: Optional[str] = None) -> bool:
    """Start the aria2 daemon with the given secret."""
    try:
        # Save secret to file
        _save_secret_to_file(secret)

        cmd = [
            "aria2c",
            "--enable-rpc",
            "--rpc-listen-port", str(rpc_port),
            "--rpc-secret", secret,
            "--rpc-allow-origin-all",
            "--dir", download_dir or str(Path.home() / "Downloads"),
            "--console-log-level", "error",
            "--log-level", "error",
            "--max-concurrent-downloads", "5",
            "--max-connection-per-server", "16",
            "--split", "5",
            "--min-split-size", "20M",
        ]
        # Start as daemon
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        logger.info("aria2 started with secret")
        return True
    except Exception as e:
        logger.error("Failed to start aria2: %s", e)
        return False


def stop_aria2() -> bool:
    """Stop aria2 daemon."""
    try:
        subprocess.run(["pkill", "-f", "aria2c"], check=False)
        return True
    except Exception as e:
        logger.error("Failed to stop aria2: %s", e)
        return False
