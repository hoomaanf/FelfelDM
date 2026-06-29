# core/aria2_manager.py
"""
Manages the aria2 subprocess with HTTPS, disk cache, dynamic settings,
and certificate generation with fingerprint pinning.
"""

import datetime
import logging
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from core.ssl_utils import get_fingerprint_from_cert

logger: logging.Logger = logging.getLogger(__name__)


class CertificateManager:
    """
    Manages SSL certificate generation, storage, and fingerprint retrieval.
    Supports custom user-provided certificates.
    """

    CONFIG_DIR: Path = Path.home() / ".config" / "felfelDM"
    CERT_DIR: Path = CONFIG_DIR / "certs"
    CERT_FILE: Path = CERT_DIR / "aria2.crt"
    KEY_FILE: Path = CERT_DIR / "aria2.key"
    FINGERPRINT_FILE: Path = CERT_DIR / "fingerprint.sha256"

    def __init__(self) -> None:
        self._fingerprint: Optional[str] = None
        self._cert_generated: bool = False
        self._custom_cert_used: bool = False
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create necessary directories with secure permissions."""
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.CERT_DIR.mkdir(parents=True, exist_ok=True)

    def _set_file_permissions(self, path: Path, mode: int = 0o600) -> None:
        """Set secure permissions for sensitive files."""
        try:
            path.chmod(mode)
        except Exception as e:
            logger.warning("Failed to set permissions on %s: %s", path, e)

    def set_custom_certificate(self, cert_path: Path, key_path: Path) -> bool:
        """
        Use a custom certificate provided by the user.

        Args:
            cert_path: Path to the certificate file (PEM format)
            key_path: Path to the private key file (PEM format)

        Returns:
            True if the certificate was loaded successfully
        """
        if not cert_path.exists() or not key_path.exists():
            logger.error("Custom certificate or key file not found")
            return False

        try:
            # Copy to the cert directory
            shutil.copy2(cert_path, self.CERT_FILE)
            shutil.copy2(key_path, self.KEY_FILE)
            self._set_file_permissions(self.CERT_FILE)
            self._set_file_permissions(self.KEY_FILE)

            # Compute fingerprint
            fingerprint = get_fingerprint_from_cert(self.CERT_FILE)
            if fingerprint:
                with open(self.FINGERPRINT_FILE, "w", encoding="utf-8") as f:
                    f.write(fingerprint)
                self._fingerprint = fingerprint
                self._cert_generated = True
                self._custom_cert_used = True
                logger.info("Custom certificate loaded with fingerprint: %s", fingerprint)
                return True
            else:
                logger.error("Failed to compute certificate fingerprint")
                return False

        except Exception as e:
            logger.error("Failed to load custom certificate: %s", e)
            return False

    def generate_certificates(self) -> bool:
        """
        Generate self-signed certificate and private key if missing.
        Also store the SHA-256 fingerprint for pinning.
        """
        # If custom certificate is already used, skip generation
        if self._custom_cert_used:
            return True

        if self.CERT_FILE.exists() and self.KEY_FILE.exists() and self.FINGERPRINT_FILE.exists():
            try:
                with open(self.FINGERPRINT_FILE, "r", encoding="utf-8") as f:
                    self._fingerprint = f.read().strip()
                self._cert_generated = True
                return True
            except Exception as e:
                logger.error("Failed to load fingerprint: %s", e)

        logger.info("Generating self-signed certificate for aria2 HTTPS...")
        try:
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )

            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "FelfelDM"),
                x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
            ])

            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName("localhost"),
                        x509.DNSName("127.0.0.1"),
                    ]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            with open(self.KEY_FILE, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            self._set_file_permissions(self.KEY_FILE)

            with open(self.CERT_FILE, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            self._set_file_permissions(self.CERT_FILE)

            fingerprint = get_fingerprint_from_cert(self.CERT_FILE)
            if fingerprint:
                with open(self.FINGERPRINT_FILE, "w", encoding="utf-8") as f:
                    f.write(fingerprint)
                self._fingerprint = fingerprint
                self._cert_generated = True
                self._custom_cert_used = False
                logger.info("Self-signed certificate generated with fingerprint: %s", fingerprint)
                return True
            else:
                logger.error("Failed to compute certificate fingerprint")
                return False

        except Exception as e:
            logger.error("Certificate generation failed: %s", e)
            return False

    def is_self_signed(self) -> bool:
        """Return True if using a self-signed certificate."""
        return self._cert_generated and not self._custom_cert_used

    @property
    def cert_file(self) -> Path:
        return self.CERT_FILE

    @property
    def key_file(self) -> Path:
        return self.KEY_FILE

    @property
    def fingerprint(self) -> Optional[str]:
        return self._fingerprint

    @property
    def is_generated(self) -> bool:
        return self._cert_generated


class Aria2Manager:
    """
    Manages the lifecycle and configuration of the aria2 subprocess.
    Now delegates certificate management to CertificateManager.
    """

    ARIA2_BIN: str = "aria2c"

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._port: int = 6800
        self._secret: str = self._generate_secret()
        self._lock: Lock = Lock()
        self._started: bool = False

        self._cert_manager = CertificateManager()
        self._cert_manager.generate_certificates()

        # Warn if using self-signed certificate
        if self._cert_manager.is_self_signed():
            logger.warning(
                "Using self-signed certificate for aria2 HTTPS. "
                "For production use, please provide a custom certificate via settings."
            )

    def _generate_secret(self) -> str:
        import secrets
        return secrets.token_urlsafe(32)

    @property
    def secret(self) -> str:
        return self._secret

    @property
    def port(self) -> int:
        return self._port

    @property
    def cert_file(self) -> Path:
        return self._cert_manager.cert_file

    @property
    def key_file(self) -> Path:
        return self._cert_manager.key_file

    @property
    def fingerprint(self) -> Optional[str]:
        return self._cert_manager.fingerprint

    def set_custom_certificate(self, cert_path: Path, key_path: Path) -> bool:
        """Set a custom certificate for aria2."""
        return self._cert_manager.set_custom_certificate(cert_path, key_path)

    def start(self) -> bool:
        """Start the aria2 subprocess with HTTPS enabled."""
        with self._lock:
            if self._started:
                return True

            if not self._cert_manager.is_generated:
                logger.error("Certificates not generated, cannot start aria2 with HTTPS")
                return False

            cmd: List[str] = [
                self.ARIA2_BIN,
                f"--rpc-listen-port={self._port}",
                f"--rpc-secret={self._secret}",
                "--rpc-secure",
                f"--rpc-certificate={self.cert_file}",
                f"--rpc-private-key={self.key_file}",
                "--rpc-allow-origin-all",
                "--rpc-listen-all=false",
                "--max-concurrent-downloads=5",
                "--max-connection-per-server=16",
                "--split=16",
                "--min-split-size=1M",
                "--continue=true",
                "--disk-cache=128M",
                "--file-allocation=falloc",
                "--enable-rpc=true",
                "--rpc-save-upload-metadata=true",
                "--follow-torrent=mem",
                "--follow-metalink=mem",
                "--bt-enable-lpd=true",
                "--bt-max-peers=50",
                "--bt-request-peer-speed-limit=100K",
                "--bt-tracker-timeout=600",
                "--dht-listen-port=6881-6999",
                "--dht-entry-point=dht.transmissionbt.com:6881",
                "--dht-file-path=~/.config/felfelDM/dht.dat",
                "--max-tries=0",
                "--retry-wait=2",
                "--timeout=60",
                "--connect-timeout=60",
            ]

            try:
                logger.info("Starting aria2 with HTTPS on port %d", self._port)
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                import time
                time.sleep(1)
                self._started = True

                # Log certificate type
                if self._cert_manager.is_self_signed():
                    logger.info("Using self-signed certificate for aria2")
                else:
                    logger.info("Using custom certificate for aria2")

                return True
            except FileNotFoundError:
                logger.error("aria2c not found in PATH")
                return False
            except Exception as e:
                logger.error("Failed to start aria2: %s", e)
                return False

    def stop(self) -> None:
        """Stop the aria2 subprocess."""
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception as e:
                    logger.warning("Error stopping aria2: %s", e)
                    try:
                        self._process.kill()
                    except Exception:
                        pass
                self._process = None
                self._started = False
                logger.info("aria2 stopped")

    def restart(self) -> bool:
        """Restart the aria2 subprocess."""
        self.stop()
        return self.start()

    def is_running(self) -> bool:
        """Check if aria2 process is running."""
        if self._process is None:
            return False
        poll = self._process.poll()
        if poll is None:
            return True
        self._started = False
        return False

    def get_port(self) -> int:
        return self._port

    def get_secret(self) -> str:
        return self._secret

    def get_fingerprint(self) -> Optional[str]:
        return self._cert_manager.fingerprint
