# core/constants.py
"""
Centralized constants for the application.
"""

from pathlib import Path

# =============================================================================
# Paths
# =============================================================================

CONFIG_DIR = Path.home() / ".config" / "felfelDM"
CACHE_DIR = Path.home() / ".cache" / "felfelDM"
CERT_DIR = CONFIG_DIR / "certs"
DATA_FILE = CONFIG_DIR / "data.json"
SESSION_FILE = CACHE_DIR / "session.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

# =============================================================================
# Keyring
# =============================================================================

KEYRING_SERVICE = "felfelDM"
KEYRING_KEY = "aria2_secret"

# =============================================================================
# aria2 RPC
# =============================================================================

DEFAULT_TIMEOUT = 15
DEFAULT_BATCH_TIMEOUT = 30
RPC_POLL_INTERVAL = 1000  # milliseconds
HEALTH_CHECK_INTERVAL = 5000  # milliseconds

# =============================================================================
# Session
# =============================================================================

SESSION_SAVE_INTERVAL = 30000  # milliseconds (30 seconds)
MAX_SESSION_AGE_DAYS = 7

# =============================================================================
# Download
# =============================================================================

DEFAULT_MAX_CONCURRENT = 5
DEFAULT_MAX_CONNECTIONS = 16
DEFAULT_SPLIT = 16
DEFAULT_DISK_CACHE = "128M"

# =============================================================================
# UI
# =============================================================================

ANIMATION_DURATION = 200  # milliseconds
SEARCH_DEBOUNCE = 300  # milliseconds
DEFAULT_THEME = "system"
DEFAULT_DOWNLOAD_PATH = Path.home() / "Downloads"

# =============================================================================
# Network
# =============================================================================

ARIA2_DEFAULT_PORT = 6800
LOCAL_SERVER_DEFAULT_PORT = 8080
ARIA2_DEFAULT_HOST = "http://localhost"

# =============================================================================
# Update
# =============================================================================

UPDATE_URL = "https://api.github.com/repos/hoomaanf/FelfelDM/releases/latest"
UPDATE_TIMEOUT = 60
CHECKSUM_TIMEOUT = 10
