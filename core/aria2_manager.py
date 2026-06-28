# Requires: cryptography>=38.0.0
"""Manages aria2 subprocess with HTTPS and certificate pinning."""

import os
import subprocess
import logging
import shutil
import socket
import time
import secrets
from pathlib import Path
from typing import Optional
from threading import Lock

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import datetime

from core.ssl_utils import get_fingerprint_from_cert
from core.data_store import DataStore

logger: logging.Logger = logging.getLogger(__name__)


class Aria2Manager:
    CONFIG_DIR: Path = Path.home() / ".config" / "felfelDM"
    CERT_DIR: Path = CONFIG_DIR / "certs"
    CERT_FILE: Path = CERT_DIR / "aria2.crt"
    KEY_FILE: Path = CERT_DIR / "aria2.key"
    FINGERPRINT_FILE: Path = CERT_DIR / "fingerprint.sha256"

    def __init__(self, aria2_binary_path: Optional[Path] = None) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._port: int = self._find_available_port()
        self._secret: str = self._load_or_generate_secret()
        self._lock: Lock = Lock()
        self._fingerprint: Optional[str] = None
        self._started: bool = False
        self._aria2_binary_path = aria2_binary_path
        self._ensure_dirs()

    def _find_available_port(self, start_port: int = 6800, max_attempts: int = 100) -> int:
        port = start_port
        for _ in range(max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                port += 1
        return start_port

    def _load_or_generate_secret(self) -> str:
        try:
            store = DataStore()
            secret = store.get_aria2_secret()
            if secret:
                logger.info("Loaded existing secret from keyring")
                return secret
        except Exception as e:
            logger.warning("Could not load secret: %s", e)

        new_secret = secrets.token_urlsafe(32)
        try:
            store = DataStore()
            store.set_aria2_secret(new_secret)
            logger.info("Generated and stored new secret")
        except Exception as e:
            logger.warning("Could not store secret: %s", e)
        return new_secret

    def _ensure_dirs(self) -> None:
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.CERT_DIR.mkdir(parents=True, exist_ok=True)

    def _set_permissions(self, path: Path, mode: int = 0o600) -> None:
        try:
            path.chmod(mode)
        except Exception:
            pass

    def _generate_certificates(self) -> bool:
        if self.CERT_FILE.exists() and self.KEY_FILE.exists() and self.FINGERPRINT_FILE.exists():
            try:
                with open(self.FINGERPRINT_FILE, "r") as f:
                    self._fingerprint = f.read().strip()
                return True
            except Exception:
                pass

        logger.info("Generating self-signed certificate...")
        try:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
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
                .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.DNSName("127.0.0.1")]), critical=False)
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            with open(self.KEY_FILE, "wb") as f:
                f.write(private_key.private_bytes(encoding=serialization.Encoding.PEM,
                                                  format=serialization.PrivateFormat.PKCS8,
                                                  encryption_algorithm=serialization.NoEncryption()))
            self._set_permissions(self.KEY_FILE)

            with open(self.CERT_FILE, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            self._set_permissions(self.CERT_FILE)

            fingerprint = get_fingerprint_from_cert(self.CERT_FILE)
            if fingerprint:
                with open(self.FINGERPRINT_FILE, "w") as f:
                    f.write(fingerprint)
                self._set_permissions(self.FINGERPRINT_FILE)
                self._fingerprint = fingerprint
                logger.info("Certificate generated")
                return True
            return False
        except Exception as e:
            logger.error("Certificate generation failed: %s", e)
            return False

    def start(self) -> bool:
        with self._lock:
            if self._started:
                return True
            if not self._generate_certificates():
                return False

            aria2_path = self._aria2_binary_path or Path(shutil.which("aria2c") or "aria2c")
            cmd = [
                str(aria2_path),
                "--enable-rpc",
                "--rpc-listen-port", str(self._port),
                "--rpc-secret", self._secret,
                "--rpc-listen-all=false",
                "--rpc-allow-origin-all=false",
                "--rpc-certificate", str(self.CERT_FILE),
                "--rpc-private-key", str(self.KEY_FILE),
                "--disable-ipv6=true",
                "--max-concurrent-downloads=5",
                "--max-connection-per-server=16",
                "--split=16",
                "--min-split-size=1M",
                "--disk-cache=64M",
                "--file-allocation=none",
                "--continue=true",
                "--max-tries=5",
                "--retry-wait=5",
                "--connect-timeout=10",
                "--timeout=10",
                "--allow-overwrite=true",
                "--auto-file-renaming=false",
            ]

            try:
                logger.info("Starting aria2: %s", " ".join(cmd))
                self._process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                time.sleep(1)
                if self._process.poll() is not None:
                    logger.error("aria2 exited immediately")
                    return False
                self._started = True
                logger.info("Aria2 started on port %d", self._port)
                return True
            except Exception as e:
                logger.error("Failed to start aria2: %s", e)
                return False

    def stop(self) -> None:
        with self._lock:
            if self._process:
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
                except Exception:
                    pass
                self._process = None
            self._started = False

    def restart(self) -> bool:
        self.stop()
        time.sleep(1)
        return self.start()

    def get_port(self) -> int:
        return self._port

    def get_secret(self) -> str:
        return self._secret

    def get_certificate_path(self) -> Optional[Path]:
        return self.CERT_FILE if self.CERT_FILE.exists() else None

    def get_certificate_fingerprint(self) -> Optional[str]:
        return self._fingerprint

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None
