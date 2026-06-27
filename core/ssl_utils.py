"""
SSL utilities for secure communication with aria2.
Provides SSL context creation with certificate pinning.
"""

import ssl
import logging
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)


def create_ssl_context(
    cert_file: Optional[Path] = None,
    fingerprint: Optional[str] = None,
) -> ssl.SSLContext:
    """
    Create an SSL context with optional certificate pinning.

    Args:
        cert_file: Path to the certificate file (PEM format) to use as CA trust store.
        fingerprint: Expected SHA-256 fingerprint of the server certificate (hex).

    Returns:
        SSLContext configured with proper verification.

    Raises:
        ValueError: If fingerprint is provided but cert_file is missing.
    """
    context = ssl.create_default_context()

    if cert_file and cert_file.exists():
        # Load the certificate as a CA trust store
        context.load_verify_locations(cafile=str(cert_file))
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = False  # We use fingerprint pinning instead
    else:
        # Fallback to system CA bundles if cert_file not provided
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True

    if fingerprint:
        if not cert_file or not cert_file.exists():
            raise ValueError(
                "Certificate file is required for fingerprint pinning"
            )
        # Store fingerprint for custom verification
        # We'll use a custom verify callback to check the fingerprint
        context.verify_flags |= ssl.VERIFY_CRL_CHECK_LEAF

        def _verify_callback(conn, cert, errnum, depth, ok):
            # In Python 3.7+, we can access the certificate via conn.getpeercert()
            # But we need to get the DER-encoded certificate
            try:
                # Get the certificate in DER format
                der_cert = conn.getpeercert(binary_form=True)
                if der_cert is None:
                    logger.error("No peer certificate available")
                    return False

                # Compute SHA-256 fingerprint
                import hashlib
                computed = hashlib.sha256(der_cert).hexdigest()
                if computed != fingerprint:
                    logger.error(
                        "Certificate fingerprint mismatch. Expected: %s, Got: %s",
                        fingerprint, computed
                    )
                    return False
                return True
            except Exception as e:
                logger.error("SSL verification failed: %s", e)
                return False

        context.verify_callback = _verify_callback

    return context


def get_fingerprint_from_cert(cert_path: Path) -> Optional[str]:
    """
    Extract SHA-256 fingerprint from a certificate file.

    Args:
        cert_path: Path to the PEM certificate file.

    Returns:
        Hexadecimal fingerprint string or None if error.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.backends import default_backend
        import hashlib

        with open(cert_path, "rb") as f:
            cert_data = f.read()
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
        der = cert.public_bytes(encoding=serialization.Encoding.DER)
        return hashlib.sha256(der).hexdigest()
    except Exception as e:
        logger.error("Failed to extract fingerprint from %s: %s", cert_path, e)
        return None
