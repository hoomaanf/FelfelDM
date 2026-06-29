# =============================================================================
# core/constants.py
# =============================================================================
from pathlib import Path

# Application directories
APP_DIR = Path.home() / ".felfeldm"
APP_DIR.mkdir(parents=True, exist_ok=True)

DATA_FILE = APP_DIR / "data.json"
BACKUP_FILE = APP_DIR / "data.backup.json"

ARIA2_CONFIG_DIR = APP_DIR / "aria2"
ARIA2_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
ARIA2_SECRET_FILE = ARIA2_CONFIG_DIR / "secret.txt"

RPC_POLL_INTERVAL = 1  # seconds

# Default settings - use Path consistently
DEFAULT_DOWNLOAD_PATH = Path.home() / "Downloads"
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_SPEED_LIMIT = 0  # 0 means unlimited

# Note: HISTORY_FILE is removed as it was unused.
# If history is needed, implement a HistoryManager class.
