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
import time
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any

import keyring
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from core.constants import (
    CONFIG_DIR,
    CERT_DIR,
    KEYRING_SERVICE,
    KEYRING_KEY,
    DEFAULT_TIMEOUT,
)

logger = logging.getLogger(__name__)


class CertificateManager:
    """
    Manages SSL certificate generation and storage for aria2 RPC.
    Uses self-signed certificates with SHA-256 fingerprint pinning.
    """

    CERT_FILE = CERT_DIR / "aria2.crt"
    KEY_FILE = CERT_DIR / "aria2.key"
    FINGERPRINT_FILE = CERT_DIR / "fingerprint.sha256"

    @classmethod
    def ensure_certificates(cls) -> bool:
        """
        Ensure certificates exist. Generate if missing.
        
        Returns:
            True if certificates are available, False otherwise
        """
        if cls._certificates_exist():
            return True
        
        logger.info("Generating self-signed certificate for aria2 HTTPS...")
        return cls._generate_certificates()

    @classmethod
    def _certificates_exist(cls) -> bool:
        """Check if certificate files exist."""
        return (
            cls.CERT_FILE.exists() and
            cls.KEY_FILE.exists() and
            cls.FINGERPRINT_FILE.exists()
        )

    @classmethod
    def _generate_certificates(cls) -> bool:
        """
        Generate self-signed certificate and private key.
        Also store the SHA-256 fingerprint for pinning.
        
        Returns:
            True on success, False on failure
        """
        try:
            CERT_DIR.mkdir(parents=True, exist_ok=True)

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
            
            cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(private_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(
                    datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365)
                )
                .add_extension(
                    x509.SubjectAlternativeName([
                        x509.DNSName("localhost"),
                        x509.DNSName("127.0.0.1"),
                    ]),
                    critical=False,
                )
                .sign(private_key, hashes.SHA256(), default_backend())
            )

            # Write private key with restricted permissions
            with open(cls.KEY_FILE, "wb") as f:
                f.write(private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            os.chmod(cls.KEY_FILE, 0o600)

            # Write certificate
            with open(cls.CERT_FILE, "wb") as f:
                f.write(cert.public_bytes(serialization.Encoding.PEM))
            os.chmod(cls.CERT_FILE, 0o644)

            # Compute SHA-256 fingerprint for certificate pinning
            der = cert.public_bytes(serialization.Encoding.DER)
            import hashlib
            fingerprint = hashlib.sha256(der).hexdigest()
            with open(cls.FINGERPRINT_FILE, "w") as f:
                f.write(fingerprint)

            logger.info("Certificate generated successfully. Fingerprint: %s", fingerprint[:16] + "...")
            return True

        except Exception as e:
            logger.error("Failed to generate certificates: %s", e)
            return False

    @classmethod
    def get_fingerprint(cls) -> Optional[str]:
        """Return the stored certificate fingerprint."""
        if cls.FINGERPRINT_FILE.exists():
            try:
                with open(cls.FINGERPRINT_FILE, "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    @classmethod
    def get_cert_path(cls) -> Optional[Path]:
        return cls.CERT_FILE if cls.CERT_FILE.exists() else None

    @classmethod
    def get_key_path(cls) -> Optional[Path]:
        return cls.KEY_FILE if cls.KEY_FILE.exists() else None


class Aria2Manager:
    """
    Manages the lifecycle and configuration of the aria2 subprocess.
    Uses CertificateManager for SSL certificates and stores secret in keyring.
    """

    ARIA2_BIN: str = "aria2c"
    DEFAULT_PORT: int = 6800

    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._port: int = port
        self._secret: Optional[str] = None
        self._lock: Lock = Lock()
        self._connected: bool = False

    def _get_or_create_secret(self) -> str:
        """
        Get secret from keyring or create a new one.
        Ensures the same secret is used across application restarts.
        
        Returns:
            The secret string
        """
        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_KEY)
            if secret:
                logger.debug("Secret retrieved from keyring")
                self._secret = secret
                return secret
        except Exception as e:
            logger.warning("Failed to retrieve secret from keyring: %s", e)

        # Generate new secret
        import secrets
        secret = secrets.token_urlsafe(32)
        
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_KEY, secret)
            logger.info("New secret generated and stored in keyring")
        except Exception as e:
            logger.warning("Failed to store secret in keyring: %s", e)
        
        self._secret = secret
        return secret

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

    def _wait_for_connection(self, timeout: int = 5) -> bool:
        """
        Wait for aria2 RPC to become available.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            True if connection successful, False otherwise
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("127.0.0.1", self._port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        return False

    def _build_command(self) -> Optional[List[str]]:
        """
        Build the aria2 command with all necessary options.
        
        Returns:
            List of command arguments, or None on failure
        """
        aria2_path = self._find_aria2()
        if not aria2_path:
            logger.error("aria2c not found in PATH. Please install aria2.")
            return None

        # Ensure certificates exist
        if not CertificateManager.ensure_certificates():
            logger.error("Failed to generate certificates")
            return None

        cert_path = CertificateManager.get_cert_path()
        key_path = CertificateManager.get_key_path()
        if not cert_path or not key_path:
            logger.error("Certificate or key file missing")
            return None

        secret = self._get_or_create_secret()

        cmd: List[str] = [
            aria2_path,
            "--enable-rpc",
            "--rpc-listen-port", str(self._port),
            "--rpc-secret", secret,
            "--rpc-secure",
            "--rpc-certificate", str(cert_path),
            "--rpc-private-key", str(key_path),
            "--rpc-listen-address", "127.0.0.1",
            "--rpc-allow-origin-all=false",
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
            "--log", str(CONFIG_DIR / "aria2.log"),
            "--log-level", "notice",
            "--console-log-level", "error",
        ]

        return cmd

    def start(self) -> bool:
        """
        Start aria2 subprocess with secure RPC.
        
        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self.is_running():
                logger.info("aria2 already running.")
                return True

            cmd = self._build_command()
            if not cmd:
                return False

            logger.info("Starting aria2 on port %d...", self._port)
            logger.debug("Command: %s", " ".join(cmd))

            try:
                # Create log directory
                (CONFIG_DIR / "logs").mkdir(parents=True, exist_ok=True)

                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )

                # Wait for connection
                if not self._wait_for_connection(timeout=5):
                    logger.error("aria2 process started but RPC not responding")
                    self._process.kill()
                    self._process = None
                    return False

                logger.info("aria2 started successfully (PID: %d)", self._process.pid)
                self._connected = True
                return True

            except Exception as e:
                logger.error("Failed to start aria2: %s", e)
                self._process = None
                self._connected = False
                return False

    def stop(self) -> None:
        """Stop the aria2 subprocess gracefully."""
        with self._lock:
            if self._process and self._process.poll() is None:
                logger.info("Stopping aria2 (PID: %d)...", self._process.pid)
                try:
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._process.kill()
                    self._process.wait()
                self._process = None
                self._connected = False
                logger.info("aria2 stopped.")

    def restart(self) -> bool:
        """Restart aria2; useful for recovery."""
        self.stop()
        time.sleep(0.5)
        return self.start()

    def get_host(self) -> str:
        return "https://localhost"

    def get_port(self) -> int:
        return self._port

    def get_secret(self) -> str:
        if self._secret is None:
            self._get_or_create_secret()
        return self._secret or ""

    def is_running(self) -> bool:
        """Check if aria2 process is running."""
        return self._process is not None and self._process.poll() is None

    def is_connected(self) -> bool:
        """Check if aria2 is running and accepting connections."""
        if not self.is_running():
            self._connected = False
            return False
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", self._port))
            sock.close()
            self._connected = (result == 0)
            return self._connected
        except Exception:
            self._connected = False
            return False

    def get_certificate_fingerprint(self) -> Optional[str]:
        """Return the certificate fingerprint for pinning."""
        return CertificateManager.get_fingerprint()
