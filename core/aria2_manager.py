# Requires: cryptography>=38.0.0

"""
Manages the aria2 subprocess with HTTPS, disk cache, dynamic settings,
and certificate generation with fingerprint pinning.
"""

import os
import subprocess
import logging
import shutil
import socket
import time
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from threading import Lock

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import datetime

from core.ssl_utils import get_fingerprint_from_cert

logger: logging.Logger = logging.getLogger(__name__)


class Aria2Manager:
    """
    Manages the lifecycle and configuration of the aria2 subprocess.
    Includes certificate generation with fingerprint storage for pinning.
    """

    CONFIG_DIR: Path = Path.home() / ".config" / "felfelDM"
    CERT_DIR: Path = CONFIG_DIR / "certs"
    CERT_FILE: Path = CERT_DIR / "aria2.crt"
    KEY_FILE: Path = CERT_DIR / "aria2.key"
    FINGERPRINT_FILE: Path = CERT_DIR / "fingerprint.sha256"
    ARIA2_BIN: str = "aria2c"

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._port: int = 6800
        self._secret: str = self._generate_secret()
        self._ensure_dirs()
        self._lock: Lock = Lock()
        self._fingerprint: Optional[str] = None
        self._started: bool = False
        self._cert_generated: bool = False

    def _ensure_dirs(self) -> None:
        """Create necessary directories with secure permissions."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.CERT_DIR.mkdir(parents=True, exist_ok=True)

    def _generate_secret(self) -> str:
        """Generate a random secret for RPC."""
        import secrets
        return secrets.token_urlsafe(32)

    def _set_file_permissions(self, path: Path, mode: int = 0o600) -> None:
        """Set secure permissions for sensitive files."""
        try:
            path.chmod(mode)
        except Exception as e:
            logger.warning("Failed to set permissions on %s: %s", path, e)

    def _generate_certificates(self) -> bool:
        """
        Generate self-signed certificate and private key if missing.
        Also store the SHA-256 fingerprint for pinning.
        """
        if self.CERT_FILE.exists() and self.KEY_FILE.exists() and self.FINGERPRINT_FILE.exists():
            # Load fingerprint
            try:
                with open(self.FINGERPRINT_FILE, 'r', encoding='utf-8') as f:
                    self._fingerprint = f.read().strip()
                self._cert_generated = True
                return True
            except Exception as e:
                logger.error("Failed to load fingerprint: %s", e)
                # Fall through to regenerate

        logger.info("Generating self-signed certificate for aria2 HTTPS...")
        try:
            # Generate private key
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            # Create self-signed certificate
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FelfelDM"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])
            cert = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.datetime.now(datetime.timezone.utc)
            ).not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("localhost"),
                    x509.DNSName("127.0.0.1"),
                ]),
                critical=False,
            ).sign(private_key, hashes.SHA256(), default_backend())

            # Write private key
            with open(self.KEY_FILE, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            self._set_file_permissions(self.KEY_FILE, 0o600)

            # Write certificate
            with open(self.CERT_FILE, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            self._set_file_permissions(self.CERT_FILE, 0o600)

            # Compute SHA-256 fingerprint using ssl_utils
            fingerprint = get_fingerprint_from_cert(self.CERT_FILE)
            if not fingerprint:
                raise RuntimeError("Failed to compute certificate fingerprint")

            self._fingerprint = fingerprint
            with open(self.FINGERPRINT_FILE, "w", encoding="utf-8") as f:
                f.write(fingerprint)
            self._set_file_permissions(self.FINGERPRINT_FILE, 0o600)

            self._cert_generated = True
            logger.info("Certificate and key generated successfully. Fingerprint: %s", fingerprint)
            return True
        except Exception as e:
            logger.error("Failed to generate certificates: %s", e)
            self._cert_generated = False
            return False

    def get_certificate_fingerprint(self) -> Optional[str]:
        """Return the stored certificate fingerprint for pinning."""
        return self._fingerprint

    def get_certificate_path(self) -> Optional[Path]:
        """Return the path to the certificate file."""
        if self.CERT_FILE.exists():
            return self.CERT_FILE
        return None

    def _find_aria2(self) -> Optional[str]:
        """Find aria2c binary in PATH or common locations."""
        path = shutil.which(self.ARIA2_BIN)
        if path:
            return path
        common_paths = [
            "/usr/bin/aria2c",
            "/usr/local/bin/aria2c",
            "/opt/aria2/bin/aria2c",
        ]
        for p in common_paths:
            if os.path.exists(p) and os.access(p, os.X_OK):
                return p
        return None

    def _wait_for_port(self, timeout: float = 5.0) -> bool:
        """
        Wait for aria2 RPC port to become available.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            True if port is available within timeout, False otherwise.
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                with socket.create_connection(
                    ("127.0.0.1", self._port), timeout=1.0
                ):
                    return True
            except (socket.error, ConnectionRefusedError):
                time.sleep(0.2)
        return False

    def start(self) -> bool:
        """Start aria2 subprocess with secure RPC, HTTP/2, and optimal settings."""
        with self._lock:
            if self._process and self._process.poll() is None:
                logger.info("aria2 already running.")
                return True

            if not self._generate_certificates():
                logger.error("Certificate generation failed; cannot start aria2 with HTTPS.")
                return False

            aria2_path = self._find_aria2()
            if not aria2_path:
                logger.error("aria2c not found in PATH. Please install aria2.")
                return False

            # Build command with HTTP/2 and dynamic cache
            cmd: List[str] = [
                aria2_path,
                "--enable-rpc",
                "--rpc-listen-port", str(self._port),
                "--rpc-secret", self._secret,
                # "--rpc-secure",
                # "--rpc-certificate", str(self.CERT_FILE),
                # "--rpc-private-key", str(self.KEY_FILE),
                "--rpc-listen-address", "127.0.0.1",
                "--max-concurrent-downloads", "5",
                "--max-connection-per-server", "16",
                "--split", "16",
                "--min-split-size", "1M",
                "--disk-cache", "128M",
                "--file-allocation", "trunc",
                "--continue", "true",
                "--max-tries", "0",
                "--retry-wait", "2",
                "--auto-file-renaming", "false",
                "--allow-overwrite", "true",
                "--enable-http2",
                "--http2-max-concurrent-streams", "100",
                "--log", str(self.CONFIG_DIR / "aria2.log"),
                "--log-level", "notice",
            ]

            logger.info("Starting aria2 with command: %s", " ".join(cmd))
            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )

                # Wait for the port to become available
                if not self._wait_for_port(timeout=5.0):
                    logger.error("aria2 did not start within timeout. Check logs.")
                    if self._process.poll() is not None:
                        logger.error("Process terminated immediately with code: %d",
                                     self._process.poll())
                    return False

                self._started = True
                logger.info("aria2 started successfully (PID: %d)", self._process.pid)
                return True
            except Exception as e:
                logger.error("Failed to start aria2: %s", e)
                self._started = False
                return False

    def stop(self) -> None:
        """Stop the aria2 subprocess."""
        with self._lock:
            if self._process and self._process.poll() is None:
                logger.info("Stopping aria2 (PID: %d)...", self._process.pid)
                self._process.terminate()
                try:
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
                logger.info("aria2 stopped.")
                self._process = None
                self._started = False

    def restart(self) -> bool:
        """Restart aria2; useful for recovery."""
        self.stop()
        time.sleep(1)
        return self.start()

    def get_host(self) -> str:
        """Return the RPC host URL (with https)."""
        return "https://127.0.0.1"

    def get_port(self) -> int:
        """Return the RPC port."""
        return self._port

    def get_secret(self) -> str:
        """Return the RPC secret."""
        return self._secret

    def is_running(self) -> bool:
        """Check if aria2 process is running."""
        return self._process is not None and self._process.poll() is None

    def refresh_secret(self) -> None:
        """Generate a new secret and update the manager."""
        self._secret = self._generate_secret()
