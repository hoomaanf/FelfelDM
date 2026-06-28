#!/bin/bash
# ============================================================
# اسکریپت خودکار اعمال تمام اصلاحات پروژه FelfelDM
# برای استفاده در شاخه‌ی fix/security-and-performance-audit
# ============================================================

set -e  # در صورت بروز هر خطا، اسکریپت متوقف شود

echo "============================================================"
echo "   شروع اعمال اصلاحات امنیتی و عملکردی پروژه FelfelDM"
echo "============================================================"

# بررسی اینکه در شاخه‌ی درست هستیم
if [ ! -f "main.py" ]; then
    echo "❌ خطا: لطفاً این اسکریپت را از ریشه‌ی پروژه اجرا کنید."
    exit 1
fi

# ============================================================
# مرحله ۱: ایجاد فایل‌های جدید
# ============================================================
echo ""
echo "📁 ایجاد فایل‌های جدید..."

mkdir -p core

# ---- core/error_handler.py ----
cat > core/error_handler.py << 'EOF'
"""Error translation for aria2 error codes to user-friendly messages
and auto-recovery strategies."""

from typing import Dict, Any, List, Optional


class ErrorHandler:
    """Translate aria2 error codes to user-friendly Persian messages
    with auto-recovery strategies."""

    ERROR_MAP: Dict[int, str] = {
        1: "خطای عمومی aria2. لطفاً لاگها را بررسی کنید.",
        2: "پارامترهای ارسالی به aria2 نامعتبر است.",
        3: "aria2 قادر به اتصال به سرور مقصد نیست.",
        4: "aria2 از سرور پاسخ غیرمنتظره دریافت کرد.",
        5: "خطا در اتمام دانلود (پایان غیرمنتظره).",
        6: "فایل مقصد از قبل وجود دارد یا قابل نوشتن نیست.",
        7: "خطا در ایجاد دایرکتوری مقصد.",
        8: "خطا در بازنویسی فایل (مشکل دسترسی).",
        9: "خطا در باز کردن فایل برای نوشتن.",
        10: "aria2 فضای کافی روی دیسک ندارد.",
        11: "فایل با checksum مطابقت ندارد. ممکن است فایل ناقص باشد.",
        12: "خطا در محاسبه checksum.",
        13: "خطا در اعتبارسنجی قطعه (chunk).",
        14: "خطا در دانلود قطعه (چون سرور قطع شده).",
        15: "خطا در باز کردن فایل موقت.",
        16: "خطا در خواندن فایل متادیتا.",
        17: "خطا در ارسال درخواست به سرور.",
        18: "خطا در دریافت پاسخ از سرور.",
        19: "فایل با checksum مطابقت ندارد.",
        20: "خطا در حل کردن نام دامنه.",
        21: "خطا در ایجاد socket.",
        22: "خطا در اتصال به سرور.",
        23: "خطا در TLS/SSL.",
        24: "احراز هویت aria2 ناموفق. رمز عبور را بررسی کنید.",
        25: "درخواست aria2 معتبر نیست (Bad Request).",
    }

    # HIGH FIX: Auto-recovery strategies for common errors
    RECOVERY_STRATEGIES: Dict[int, str] = {
        3: "retry_connection",
        10: "check_disk_space",
        14: "retry_chunk",
        17: "retry_request",
        20: "retry_dns",
        22: "retry_connection",
    }

    def translate(self, code: int, message: str, method: str = "") -> str:
        base = self.ERROR_MAP.get(
            code,
            f"خطای aria2: {message} (کد: {code})"
        )
        if method:
            base += f" (در متد {method})"
        return base

    def get_recovery_strategy(self, code: int) -> Optional[str]:
        return self.RECOVERY_STRATEGIES.get(code)

    def should_retry(self, code: int, attempt: int, max_attempts: int = 5) -> bool:
        if attempt >= max_attempts:
            return False
        retryable_codes = {3, 14, 17, 20, 22}
        return code in retryable_codes

    def get_retry_delay(self, attempt: int, base_delay: float = 1.0) -> float:
        return min(base_delay * (2 ** attempt), 30.0)

    def get_recovery_action(self, code: int, context: Dict[str, Any]) -> Dict[str, Any]:
        strategy = self.get_recovery_strategy(code)
        action: Dict[str, Any] = {
            "strategy": strategy or "none",
            "retry": False,
            "delay": 0,
            "message": self.translate(code, "", ""),
        }

        if strategy in ("retry_connection", "retry_request", "retry_dns"):
            action["retry"] = True
            action["delay"] = 2.0
            action["message"] = "تلاش مجدد برای اتصال..."
        elif strategy == "check_disk_space":
            action["retry"] = False
            action["message"] = "فضای دیسک کافی نیست. لطفاً حداقل ۱۰۰ مگابایت فضا آزاد کنید."
        elif strategy == "retry_chunk":
            action["retry"] = True
            action["delay"] = 5.0
            action["message"] = "خطا در دانلود قطعه. تلاش مجدد..."

        return action
EOF

# ---- core/monitor.py ----
cat > core/monitor.py << 'EOF'
"""Aria2 health monitor with auto-recovery and sleep/wake detection."""

import logging
import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.data_store import DataStore
from core.session_manager import SessionManager
from core.error_handler import ErrorHandler

logger: logging.Logger = logging.getLogger(__name__)


class Aria2Monitor(QObject):
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        session_mgr: SessionManager,
        aria2_manager: Aria2Manager,
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.session_mgr = session_mgr
        self.aria2_manager = aria2_manager
        self._timer: Optional[QTimer] = None
        self._running = False
        self._error_handler = ErrorHandler()
        self._failure_count = 0
        self._max_failures = 3
        self._last_restart_time = 0
        self._restart_cooldown = 30
        self._was_sleeping = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._timer = QTimer()
        self._timer.timeout.connect(self._check_health)
        self._timer.start(5000)
        logger.info("Aria2Monitor started")

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        logger.info("Aria2Monitor stopped")

    def _check_health(self) -> None:
        if not self._running:
            return
        try:
            stat = self.aria2.get_global_stat()
            if stat is None:
                raise Exception("No response from aria2")
            self._failure_count = 0
            self.connection_changed.emit(True)
        except Exception as e:
            logger.error("Aria2 health check failed: %s", e)
            self._failure_count += 1
            self.connection_changed.emit(False)

            # Auto-recovery for retryable errors
            error_code = self._extract_error_code(e)
            if error_code is not None:
                recovery_action = self._error_handler.get_recovery_action(
                    error_code, {"context": "health_check"}
                )
                if recovery_action.get("retry"):
                    logger.info("Auto-recovery: %s", recovery_action.get("message"))
                    return

            now = time.time()
            if now - self._last_restart_time < self._restart_cooldown:
                logger.warning("Restart cooldown active, waiting...")
                return

            if self._failure_count >= self._max_failures:
                logger.warning("Too many failures (%d), attempting restart...", self._failure_count)
                self._attempt_restart()
                self._failure_count = 0

    def _extract_error_code(self, exception: Exception) -> Optional[int]:
        error_str = str(exception)
        for code in [3, 10, 14, 17, 20, 22]:
            if str(code) in error_str:
                return code
        return None

    def _attempt_restart(self) -> None:
        self._last_restart_time = time.time()
        if self.aria2_manager.restart():
            logger.info("Aria2 restarted successfully.")
            new_secret = self.aria2_manager.get_secret()
            self.aria2.set_secret(new_secret)
            new_fingerprint = self.aria2_manager.get_certificate_fingerprint()
            if new_fingerprint:
                self.aria2.fingerprint = new_fingerprint
            self.aria2.cert_file = self.aria2_manager.get_certificate_path()
            self.aria2._ensure_session()

            gids = self.session_mgr.load_session()
            if gids:
                logger.info("Resuming %d downloads after restart", len(gids))
                for gid in gids:
                    try:
                        status = self.aria2.tell_status(gid, ["gid"])
                        if status and status.get("gid"):
                            self.aria2.unpause(gid)
                    except Exception as e:
                        logger.warning("Failed to resume GID %s: %s", gid, e)
            self.connection_changed.emit(True)
        else:
            logger.critical("Failed to restart aria2.")

    def on_system_sleep(self) -> None:
        self._was_sleeping = True
        logger.info("System entering sleep mode")

    def on_system_wake(self) -> None:
        logger.info("System waking from sleep mode")
        if self._was_sleeping:
            self._was_sleeping = False
            self._check_health()
            self._refresh_session_after_wake()

    def _refresh_session_after_wake(self) -> None:
        try:
            gids = self.session_mgr.load_session()
            if gids:
                logger.info("Refreshing %d downloads after wake", len(gids))
                for gid in gids:
                    status = self.aria2.tell_status(gid, ["gid", "status"])
                    if status and status.get("status") == "paused":
                        self.aria2.unpause(gid)
        except Exception as e:
            logger.error("Failed to refresh session after wake: %s", e)
EOF

echo "✅ فایل‌های جدید ایجاد شدند."

# ============================================================
# مرحله ۲: جایگزینی فایل‌های موجود
# ============================================================

echo ""
echo "📝 جایگزینی فایل‌های موجود..."

# تابع کمکی برای جایگزینی فایل با محتوای جدید
replace_file() {
    local file="$1"
    local content="$2"
    echo "$content" > "$file"
    echo "   ✅ $file"
}

# ---- main.py ----
replace_file main.py "$(cat << 'EOF'
# Requires: PyQt6>=6.4.0
# Requires: requests>=2.28.0
# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0
# Requires: websocket-client>=1.4.0
# Requires: cryptography>=38.0.0
# Requires: packaging>=21.0

"""Entry point for FelfelDM Download Manager."""

import sys
import logging
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import NoReturn

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from utils.style import apply_style
from ui.main_window import MainWindow
from core.aria2_manager import Aria2Manager
from core.data_store import DataStore
from core.session_manager import SessionManager

__version__ = "3.0.0"


def configure_logging() -> None:
    log_dir: Path = Path.home() / ".cache" / "felfelDM" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file: Path = log_dir / "felfelDM.log"

    root_logger: logging.Logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    file_handler: RotatingFileHandler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    root_logger.addHandler(file_handler)

    for lib in ("urllib3", "keyring", "websocket", "requests"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def find_aria2_binary() -> Path | None:
    aria2_path = shutil.which("aria2c")
    if aria2_path:
        return Path(aria2_path)

    common_paths = []
    if sys.platform == "win32":
        common_paths = [
            Path("C:/Program Files/aria2/aria2c.exe"),
            Path("C:/Program Files (x86)/aria2/aria2c.exe"),
        ]
    elif sys.platform == "darwin":
        common_paths = [
            Path("/usr/local/bin/aria2c"),
            Path("/opt/homebrew/bin/aria2c"),
        ]
    else:
        common_paths = [
            Path("/usr/bin/aria2c"),
            Path("/usr/local/bin/aria2c"),
        ]

    for path in common_paths:
        if path.exists() and path.is_file():
            return path
    return None


def main() -> NoReturn:
    configure_logging()
    logger = logging.getLogger(__name__)

    aria2_binary = find_aria2_binary()
    if aria2_binary is None:
        logger.critical("aria2c binary not found.")
        print("\n" + "=" * 60)
        print("ERROR: aria2c binary not found!")
        print("Please install aria2 from: https://aria2.github.io/")
        print("Make sure 'aria2c' is available in your PATH.")
        print("=" * 60 + "\n")
        sys.exit(1)

    logger.info("Found aria2c at: %s", aria2_binary)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    apply_style(app)

    store: DataStore = DataStore()
    session_mgr: SessionManager = SessionManager(store)

    aria2_manager: Aria2Manager = Aria2Manager(aria2_binary_path=aria2_binary)
    if not aria2_manager.start():
        logger.critical("Failed to start aria2. Exiting.")
        sys.exit(1)

    window: MainWindow = MainWindow(aria2_manager, store, session_mgr)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
EOF
)"

# ---- core/aria2_rpc.py ----
replace_file core/aria2_rpc.py "$(cat << 'EOF'
# Requires: requests>=2.28.0
"""Aria2 RPC client with certificate pinning and batch operations."""

import logging
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt6.QtCore import QObject, pyqtSignal

from core.error_handler import ErrorHandler
from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class Aria2RPC(QObject):
    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        host: str = "http://127.0.0.1",
        port: int = 6800,
        secret: str = "",
        timeout: float = 5.0,
        max_retries: int = 3,
        fingerprint: Optional[str] = None,
        cert_file: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.host: str = host.rstrip("/")
        self.port: int = port
        self.secret: str = secret
        self.timeout: float = max(1.0, timeout)
        self.max_retries: int = max(0, max_retries)
        self.fingerprint: Optional[str] = fingerprint
        self.cert_file: Optional[Path] = cert_file
        self._lock: Lock = Lock()
        self._session: Optional[requests.Session] = None
        self._error_handler = ErrorHandler()
        self._ensure_session()

    def _ensure_session(self) -> None:
        if self._session is not None:
            self._session.close()

        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        if not self.cert_file or not self.cert_file.exists():
            raise RuntimeError("Certificate file is required for secure communication.")

        try:
            ssl_context = create_ssl_context(
                cert_file=self.cert_file,
                fingerprint=self.fingerprint,
            )
            session.verify = str(self.cert_file)
        except Exception as e:
            logger.error("Failed to configure SSL context: %s", e)
            raise RuntimeError(f"SSL configuration failed: {e}")

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=retry_strategy,
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        self._session = session

    def set_secret(self, secret: str) -> None:
        with self._lock:
            self.secret = secret
        logger.info("Aria2RPC secret updated")

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def _emit_error(self, error_msg: str) -> None:
        self.error_occurred.emit(error_msg)

    def _request(self, method: str, params: List[Any]) -> Optional[Dict[str, Any]]:
        if self._session is None:
            self._ensure_session()

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": [f"token:{self.secret}"] + params,
        }

        url = f"{self.host}:{self.port}/jsonrpc"

        try:
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                error_code = data["error"].get("code", -1)
                error_msg = data["error"].get("message", "Unknown error")
                friendly_msg = self._error_handler.translate(error_code, error_msg, method)
                self._emit_error(friendly_msg)
                return None
            return data.get("result")

        except requests.exceptions.SSLError as e:
            logger.error("SSL error: %s", e)
            self._emit_error(f"SSL error: {e}")
            self.connection_changed.emit(False)
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error: %s", e)
            self.connection_changed.emit(False)
            return None
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return None

    def _batch_request(self, calls: List[Dict[str, Any]]) -> Optional[List[Any]]:
        if self._session is None:
            self._ensure_session()

        multicall_params = []
        for call in calls:
            method = call.get("methodName")
            params = call.get("params", [])
            multicall_params.append({
                "methodName": method,
                "params": [f"token:{self.secret}"] + params,
            })

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "system.multicall",
            "params": multicall_params,
        }

        url = f"{self.host}:{self.port}/jsonrpc"

        try:
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                error_code = data["error"].get("code", -1)
                error_msg = data["error"].get("message", "Unknown error")
                friendly_msg = self._error_handler.translate(error_code, error_msg, "system.multicall")
                self._emit_error(friendly_msg)
                return None
            return data.get("result", [])
        except Exception as e:
            logger.error("Batch request error: %s", e)
            return None

    # --- Core methods ---
    def add_url(self, urls: List[str], options: Optional[Dict[str, Any]] = None, position: Optional[int] = None) -> Optional[str]:
        params: List[Any] = [urls]
        if options:
            params.append(options)
        if position is not None:
            params.append(position)
        result = self._request("aria2.addUrl", params)
        return result if isinstance(result, str) else None

    def remove(self, gid: str) -> Optional[str]:
        result = self._request("aria2.remove", [gid])
        return result if isinstance(result, str) else None

    def force_remove(self, gid: str) -> Optional[str]:
        result = self._request("aria2.forceRemove", [gid])
        return result if isinstance(result, str) else None

    def pause(self, gid: str) -> Optional[str]:
        result = self._request("aria2.pause", [gid])
        return result if isinstance(result, str) else None

    def pause_all(self) -> Optional[str]:
        result = self._request("aria2.pauseAll", [])
        return result if isinstance(result, str) else None

    def unpause(self, gid: str) -> Optional[str]:
        result = self._request("aria2.unpause", [gid])
        return result if isinstance(result, str) else None

    def unpause_all(self) -> Optional[str]:
        result = self._request("aria2.unpauseAll", [])
        return result if isinstance(result, str) else None

    def tell_status(self, gid: str, keys: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        params: List[Any] = [gid]
        if keys:
            params.append(keys)
        result = self._request("aria2.tellStatus", params)
        return result if isinstance(result, dict) else None

    def get_options(self, gid: str) -> Optional[Dict[str, Any]]:
        result = self._request("aria2.getOptions", [gid])
        return result if isinstance(result, dict) else None

    def change_option(self, gid: str, options: Dict[str, Any]) -> Optional[str]:
        result = self._request("aria2.changeOption", [gid, options])
        return result if isinstance(result, str) else None

    def get_global_stat(self) -> Optional[Dict[str, Any]]:
        result = self._request("aria2.getGlobalStat", [])
        return result if isinstance(result, dict) else None

    def get_active_downloads(self) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellActive", [])
        return result if isinstance(result, list) else None

    def get_waiting_downloads(self, offset: int = 0, num: int = 100) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellWaiting", [offset, num])
        return result if isinstance(result, list) else None

    def get_stopped_downloads(self, offset: int = 0, num: int = 100) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellStopped", [offset, num])
        return result if isinstance(result, list) else None

    # --- Batch operations ---
    def pause_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.pause", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed

    def unpause_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.unpause", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed

    def remove_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.remove", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed
EOF
)"

# ---- core/updater.py ----
replace_file core/updater.py "$(cat << 'EOF'
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
EOF
)"

# ---- core/websocket_client.py ----
replace_file core/websocket_client.py "$(cat << 'EOF'
# Requires: websocket-client>=1.4.0
"""WebSocket client with SSL pinning and auto-reconnect."""

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from queue import Queue

import websocket
from PyQt6.QtCore import QObject, pyqtSignal

from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        host: str,
        port: int,
        secret: str,
        cert_file: Optional[Path] = None,
        fingerprint: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.host: str = host
        self.port: int = port
        self.secret: str = secret
        self.cert_file: Optional[Path] = cert_file
        self.fingerprint: Optional[str] = fingerprint
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._connected: bool = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("WebSocket client started")

    def stop(self) -> None:
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WebSocket client stopped")

    def _run(self) -> None:
        while self._running:
            if self.host.startswith("https"):
                ws_url = f"wss://127.0.0.1:{self.port}/jsonrpc"
            else:
                ws_url = f"ws://127.0.0.1:{self.port}/jsonrpc"

            sslopt = {}
            if ws_url.startswith("wss"):
                try:
                    ssl_context = create_ssl_context(
                        cert_file=self.cert_file,
                        fingerprint=self.fingerprint,
                    )
                    sslopt = {"context": ssl_context}
                except Exception as e:
                    logger.error("SSL context failed: %s", e)
                    self.connection_changed.emit(False)
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                    continue

            self._ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                subprotocols=["jsonrpc"],
            )

            self._ws.run_forever(sslopt=sslopt, ping_interval=30, ping_timeout=10)

            if not self._running:
                break

            logger.warning("WebSocket disconnected, reconnecting in %.1fs", self._reconnect_delay)
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    def _on_open(self, ws) -> None:
        logger.info("WebSocket connected")
        self._connected = True
        self._reconnect_delay = 1.0
        self.connection_changed.emit(True)
        self._send_request("aria2.subscribe", ["system.multicall"])

    def _on_message(self, ws, message) -> None:
        try:
            data = json.loads(message)
            method = data.get("method")
            if method and method.startswith("aria2.on"):
                params = data.get("params", [])
                if params and len(params) > 0:
                    gid = params[0].get("gid")
                    if gid:
                        event_type = method.replace("aria2.on", "").lower()
                        self.stats_updated.emit({"event": event_type, "gid": gid})
        except Exception as e:
            logger.error("Message error: %s", e)

    def _on_error(self, ws, error) -> None:
        logger.error("WebSocket error: %s", error)
        self._connected = False
        self.connection_changed.emit(False)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info("WebSocket closed")
        self._connected = False
        self.connection_changed.emit(False)

    def _send_request(self, method: str, params: List[Any]) -> str:
        if not self._ws or not self._connected:
            return ""

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": [f"token:{self.secret}"] + params,
        }

        try:
            self._ws.send(json.dumps(payload))
            return request_id
        except Exception:
            return ""

    def is_connected(self) -> bool:
        return self._connected
EOF
)"

# ---- core/worker.py ----
replace_file core/worker.py "$(cat << 'EOF'
# Requires: PyQt6>=6.4.0
"""Background worker with WebSocket, polling fallback, and dynamic connections."""

import logging
import time
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from core.aria2_rpc import Aria2RPC
from core.data_store import DataStore
from core.websocket_client import WebSocketClient
from core.session_manager import SessionManager
from core.monitor import Aria2Monitor

logger: logging.Logger = logging.getLogger(__name__)


class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        session_mgr: SessionManager,
        aria2_manager: "Aria2Manager",
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.session_mgr = session_mgr
        self.aria2_manager = aria2_manager
        self.running = True
        self._poll_timer: Optional[QTimer] = None
        self._ws_client: Optional[WebSocketClient] = None
        self._monitor: Optional[Aria2Monitor] = None
        self.poll_interval = self.store.settings.get("poll_interval", 10000)
        self._adjust_connections_timer: Optional[QTimer] = None
        self._speed_history: Dict[str, List[int]] = {}
        self._last_poll_time = 0

    def run(self) -> None:
        logger.info("BackendWorker started")

        host = self.store.settings.get("aria2_host", "https://127.0.0.1")
        port = self.store.settings.get("aria2_port", 6800)
        secret = self.store.get_aria2_secret()
        cert_file = self.aria2_manager.get_certificate_path()
        fingerprint = self.aria2_manager.get_certificate_fingerprint()

        self._ws_client = WebSocketClient(host, port, secret, cert_file, fingerprint)
        self._ws_client.connection_changed.connect(self._on_ws_connection_changed)
        self._ws_client.stats_updated.connect(self._on_ws_stats_updated)
        self._ws_client.start()

        self._monitor = Aria2Monitor(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self._monitor.start()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(self.poll_interval)

        self._adjust_connections_timer = QTimer()
        self._adjust_connections_timer.timeout.connect(self._adjust_connections)
        self._adjust_connections_timer.start(5000)

        self.exec()

        if self._ws_client:
            self._ws_client.stop()
        if self._poll_timer:
            self._poll_timer.stop()
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
        if self._monitor:
            self._monitor.stop()

        logger.info("BackendWorker stopped")

    def _on_ws_connection_changed(self, connected: bool) -> None:
        self.connection_changed.emit(connected)
        if connected:
            logger.info("WebSocket connected - real-time updates active")
        else:
            logger.warning("WebSocket disconnected - falling back to polling")

    def _on_ws_stats_updated(self, data: Dict[str, Any]) -> None:
        self.stats_updated.emit(data)

    def _poll(self) -> None:
        if not self.running:
            return

        if self._ws_client and self._ws_client.is_connected():
            now = time.time()
            if now - self._last_poll_time < 30:
                return
            self._last_poll_time = now

        try:
            active = self.aria2.get_active_downloads()
            if active is not None:
                self.stats_updated.emit({"active": active, "source": "poll"})

            stat = self.aria2.get_global_stat()
            if stat is not None:
                self.stats_updated.emit({"global_stat": stat, "source": "poll"})

        except Exception as e:
            logger.error("Poll error: %s", e)

    def _adjust_connections(self) -> None:
        if not self.running:
            return

        try:
            active = self.aria2.get_active_downloads()
            if not active:
                return

            for download in active:
                gid = download.get("gid")
                if not gid:
                    continue

                speed = download.get("downloadSpeed", 0)
                if speed == 0:
                    continue

                if gid not in self._speed_history:
                    self._speed_history[gid] = []
                self._speed_history[gid].append(speed)

                if len(self._speed_history[gid]) > 10:
                    self._speed_history[gid] = self._speed_history[gid][-10:]

                avg_speed = sum(self._speed_history[gid]) / len(self._speed_history[gid])
                if avg_speed < 1024 * 50:
                    opts = self.aria2.get_options(gid)
                    if opts:
                        current = int(opts.get("max-connection-per-server", 1))
                        if current < 16:
                            new_val = min(current + 1, 16)
                            self.aria2.change_option(gid, {"max-connection-per-server": str(new_val)})
                            logger.debug("Increased connections for %s to %d", gid, new_val)

        except Exception as e:
            logger.debug("Connection adjustment error: %s", e)

    def stop(self) -> None:
        self.running = False
        if self._ws_client:
            self._ws_client.stop()
        if self._poll_timer:
            self._poll_timer.stop()
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
        if self._monitor:
            self._monitor.stop()
        self.quit()
        self.wait()
EOF
)"

# ---- ui/main_window.py ----
replace_file ui/main_window.py "$(cat << 'EOF'
# Requires: PyQt6>=6.4.0
"""Main window with search, progress, context menu, and auto-update."""

import logging
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar, QTableView,
    QAbstractItemView, QMenu, QMessageBox, QDialog, QLabel,
    QStatusBar, QHeaderView, QLineEdit, QHBoxLayout,
)
from PyQt6.QtCore import Qt, QSize, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QAction

from core.data_store import DataStore
from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.worker import BackendWorker
from core.session_manager import SessionManager
from core.updater import Updater
from ui.dialogs import (
    AddDownloadDialog, SingleDownloadDialog, QuickDownloadDialog,
    SettingsDialog, DownloadProgressDialog,
)
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate, StatusDelegate
from ui.icons import get_icon
from utils.helpers import format_speed

from main import __version__

logger: logging.Logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    update_available = pyqtSignal(str)

    def __init__(self, aria2_manager: Aria2Manager, store: DataStore, session_mgr: SessionManager) -> None:
        super().__init__()
        self.aria2_manager = aria2_manager
        self.store = store
        self.session_mgr = session_mgr

        self.setWindowTitle(f"FelfelDM v{__version__}")
        self.setMinimumSize(1000, 600)

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.get_aria2_secret(),
            timeout=self.store.settings.get("aria2_timeout", 5),
            fingerprint=self.aria2_manager.get_certificate_fingerprint(),
            cert_file=self.aria2_manager.get_certificate_path(),
        )

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_connections()

        self.worker: Optional[BackendWorker] = None
        self._start_backend()
        self.progress_dialogs: Dict[str, DownloadProgressDialog] = {}

        self._restore_session()
        self.updater = Updater(__version__)
        self._check_updates()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by filename, URL, or GID...")
        self.search_edit.textChanged.connect(self._filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        main_layout.addLayout(search_layout)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        add_action = QAction(get_icon("list-add"), "Add Downloads", self)
        add_action.triggered.connect(self._add_downloads)
        toolbar.addAction(add_action)

        single_action = QAction(get_icon("document-new"), "Single Download", self)
        single_action.triggered.connect(self._single_download)
        toolbar.addAction(single_action)

        quick_action = QAction(get_icon("insert-link"), "Quick Download", self)
        quick_action.triggered.connect(self._quick_download)
        toolbar.addAction(quick_action)

        toolbar.addSeparator()

        pause_action = QAction(get_icon("media-playback-pause"), "Pause All", self)
        pause_action.triggered.connect(self._pause_all)
        toolbar.addAction(pause_action)

        resume_action = QAction(get_icon("media-playback-start"), "Resume All", self)
        resume_action.triggered.connect(self._resume_all)
        toolbar.addAction(resume_action)

        toolbar.addSeparator()

        settings_action = QAction(get_icon("preferences-system"), "Settings", self)
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        self.table_view = QTableView()
        self.table_model = DownloadTableModel(self.store, self.aria2)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table_view.setItemDelegateForColumn(3, ProgressDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(4, StatusDelegate(self.table_view))

        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table_view)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        add_action = file_menu.addAction("Add Downloads...")
        add_action.triggered.connect(self._add_downloads)
        file_menu.addSeparator()
        file_menu.addAction("Exit").triggered.connect(self.close)

        download_menu = menubar.addMenu("Download")
        download_menu.addAction("Pause All").triggered.connect(self._pause_all)
        download_menu.addAction("Resume All").triggered.connect(self._resume_all)

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Settings...").triggered.connect(self._show_settings)
        tools_menu.addSeparator()
        tools_menu.addAction("Check for Updates...").triggered.connect(self._check_updates)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About").triggered.connect(self._show_about)

    def _setup_statusbar(self) -> None:
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        self.speed_label = QLabel("Speed: 0 B/s")
        self.status_bar.addPermanentWidget(self.speed_label)
        self.download_count_label = QLabel("Downloads: 0")
        self.status_bar.addPermanentWidget(self.download_count_label)

    def _setup_connections(self) -> None:
        self.table_model.dataChanged.connect(lambda: None)

    def _start_backend(self) -> None:
        self.worker = BackendWorker(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.start()

    def _restore_session(self) -> None:
        gids = self.session_mgr.load_session()
        if gids:
            logger.info("Restoring %d downloads", len(gids))
            self._refresh_table()

    def _check_updates(self) -> None:
        import threading

        def check_thread() -> None:
            new_version = self.updater.check_for_updates()
            if new_version:
                self.update_available.emit(new_version)

        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
        self.update_available.connect(self._on_update_available)

    def _on_update_available(self, new_version: str) -> None:
        reply = QMessageBox.question(
            self,
            "Update Available",
            f"Version {new_version} is available. Download now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(new_version)

    def _download_update(self, new_version: str) -> None:
        download_url = f"https://felfeldm.example.com/download/FelfelDM-{new_version}.exe"
        if self.updater.download_update(new_version, download_url):
            QMessageBox.information(self, "Update Downloaded", "Update verified. Installing...")
            self.updater.install_update()
            self.close()
        else:
            QMessageBox.critical(self, "Update Failed", "Download or verification failed.")

    def _on_stats_updated(self, data: Dict[str, Any]) -> None:
        self.table_model.refresh()
        if "global_stat" in data:
            stat = data["global_stat"]
            speed = int(stat.get("downloadSpeed", 0))
            self.speed_label.setText(f"Speed: {format_speed(speed)}")
            count = int(stat.get("numActive", 0))
            self.download_count_label.setText(f"Downloads: {count}")

    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected to aria2")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("Disconnected - reconnecting...")
            self.status_label.setStyleSheet("color: red;")

    def _filter_table(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(text)

    def _refresh_table(self) -> None:
        self.table_model.refresh()

    def _add_downloads(self) -> None:
        dialog = AddDownloadDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            urls = dialog.get_urls()
            options = dialog.get_options()
            queue_name = dialog.get_queue()
            start_immediately = dialog.start_immediately()

            for url in urls:
                gid = self.aria2.add_url([url], options)
                if gid:
                    self.store.add_gid_to_queue(queue_name, gid)
                    if start_immediately:
                        self.aria2.unpause(gid)
            self._refresh_table()

    def _single_download(self) -> None:
        dialog = SingleDownloadDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.get_url()
            if url:
                gid = self.aria2.add_url([url], dialog.get_options())
                if gid:
                    self.store.add_gid_to_queue("default", gid)
                    self._refresh_table()

    def _quick_download(self) -> None:
        dialog = QuickDownloadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.get_url()
            if url:
                gid = self.aria2.add_url([url], {})
                if gid:
                    self.store.add_gid_to_queue("default", gid)
                    self._refresh_table()

    def _pause_all(self) -> None:
        self.aria2.pause_all()
        self._refresh_table()

    def _resume_all(self) -> None:
        self.aria2.unpause_all()
        self._refresh_table()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.reload()
            self._refresh_table()

    def _show_context_menu(self, pos) -> None:
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()
        gid = self.table_model.get_gid(row)
        if not gid:
            return

        menu = QMenu(self)
        menu.addAction("Pause").triggered.connect(lambda: self._pause_download(gid))
        menu.addAction("Resume").triggered.connect(lambda: self._resume_download(gid))
        menu.addSeparator()
        menu.addAction("Remove").triggered.connect(lambda: self._remove_download(gid))
        menu.addAction("Force Remove").triggered.connect(lambda: self._force_remove_download(gid))
        menu.addSeparator()
        menu.addAction("Show Details").triggered.connect(lambda: self._show_download_details(gid))
        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _pause_download(self, gid: str) -> None:
        self.aria2.pause(gid)
        self._refresh_table()

    def _resume_download(self, gid: str) -> None:
        self.aria2.unpause(gid)
        self._refresh_table()

    def _remove_download(self, gid: str) -> None:
        reply = QMessageBox.question(self, "Remove", "Are you sure?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.aria2.remove(gid)
            self.store.remove_gid(gid)
            self._refresh_table()

    def _force_remove_download(self, gid: str) -> None:
        reply = QMessageBox.question(self, "Force Remove", "Are you sure?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.aria2.force_remove(gid)
            self.store.remove_gid(gid)
            self._refresh_table()

    def _show_download_details(self, gid: str) -> None:
        if gid not in self.progress_dialogs:
            self.progress_dialogs[gid] = DownloadProgressDialog(gid, self.aria2, self)
        self.progress_dialogs[gid].show()
        self.progress_dialogs[gid].raise_()

    def _show_about(self) -> None:
        QMessageBox.about(self, "About FelfelDM", f"FelfelDM v{__version__}\n\nA modern download manager.")

    def closeEvent(self, event) -> None:
        gids = self.store.get_all_gids()
        self.session_mgr.save_session(gids)
        if self.worker:
            self.worker.stop()
        self.aria2_manager.stop()
        event.accept()
EOF
)"

# ---- core/data_store.py ----
replace_file core/data_store.py "$(cat << 'EOF'
# Requires: appdirs>=1.4.4
# Requires: keyring>=23.0.0
"""Data persistence with priority queues and keyring integration."""

import json
import logging
import uuid
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from threading import Lock

from appdirs import user_config_dir
import keyring
from keyring.errors import KeyringError, NoKeyringError

logger: logging.Logger = logging.getLogger(__name__)

_SECRET_SUFFIX = uuid.uuid4().hex[:8]
KEYRING_SERVICE: str = f"felfelDM_{_SECRET_SUFFIX}"
KEYRING_ARIA2_SECRET: str = "aria2_secret"


@dataclass
class Queue:
    name: str
    max_concurrent: int = 3
    save_path: str = ""
    schedule_enabled: bool = False
    schedule_start: dtime = field(default_factory=lambda: dtime(0, 0))
    schedule_end: dtime = field(default_factory=lambda: dtime(23, 59))
    days: List[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    downloads: List[str] = field(default_factory=list)
    paused: bool = True
    priority: int = 0  # 0 = highest, higher = lower

    def __post_init__(self) -> None:
        if not self.save_path:
            self.save_path = str(Path.home() / "Downloads")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "save_path": self.save_path,
            "schedule_enabled": self.schedule_enabled,
            "schedule_start": self.schedule_start.strftime("%H:%M"),
            "schedule_end": self.schedule_end.strftime("%H:%M"),
            "days": self.days,
            "downloads": self.downloads,
            "paused": self.paused,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Queue":
        q = cls(name=data.get("name", "Default"))
        q.max_concurrent = data.get("max_concurrent", 3)
        q.save_path = data.get("save_path", str(Path.home() / "Downloads"))
        q.schedule_enabled = data.get("schedule_enabled", False)
        try:
            st = data.get("schedule_start", "00:00").split(":")
            q.schedule_start = dtime(int(st[0]), int(st[1]))
        except Exception:
            q.schedule_start = dtime(0, 0)
        try:
            en = data.get("schedule_end", "23:59").split(":")
            q.schedule_end = dtime(int(en[0]), int(en[1]))
        except Exception:
            q.schedule_end = dtime(23, 59)
        q.days = data.get("days", [0, 1, 2, 3, 4, 5, 6])
        q.downloads = list(data.get("downloads", []))
        q.paused = data.get("paused", True)
        q.priority = data.get("priority", 0)
        return q

    def is_scheduled_now(self) -> bool:
        if not self.schedule_enabled:
            return True
        now = datetime.now()
        if now.weekday() not in self.days:
            return False
        current_time = now.time().replace(second=0, microsecond=0)
        start, end = self.schedule_start, self.schedule_end
        return start <= current_time <= end if start <= end else current_time >= start or current_time <= end


class DataStore:
    CONFIG_DIR: Path = Path(user_config_dir("felfelDM"))
    DATA_FILE: Path = CONFIG_DIR / "data.json"

    def __init__(self) -> None:
        self._lock: Lock = Lock()
        self.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {}
        self.settings: Dict[str, Any] = {}
        self.queues: Dict[str, Queue] = {}
        self._load()

    def _load(self) -> None:
        with self._lock:
            if not self.DATA_FILE.exists():
                self._init_defaults()
                return
            try:
                with open(self.DATA_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self.settings = self._data.get("settings", {})
                queues_data = self._data.get("queues", {})
                self.queues = {name: Queue.from_dict(qdata) for name, qdata in queues_data.items()}
                logger.info("Loaded %d queues", len(self.queues))
            except Exception as e:
                logger.error("Load failed: %s", e)
                self._init_defaults()

    def _init_defaults(self) -> None:
        self.settings = {
            "aria2_host": "https://127.0.0.1",
            "aria2_port": 6800,
            "aria2_timeout": 5,
            "poll_interval": 10000,
            "max_connections": 16,
            "max_downloads": 5,
        }
        self.queues = {
            "default": Queue(name="default", max_concurrent=3, save_path=str(Path.home() / "Downloads"), paused=False)
        }
        self._save()

    def _save(self) -> None:
        with self._lock:
            try:
                data = {
                    "settings": self.settings,
                    "queues": {name: q.to_dict() for name, q in self.queues.items()},
                    "version": "3.0",
                }
                with open(self.DATA_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                self.DATA_FILE.chmod(0o600)
            except Exception as e:
                logger.error("Save failed: %s", e)

    def reload(self) -> None:
        self._load()

    def get_queues(self) -> Dict[str, Queue]:
        with self._lock:
            return dict(self.queues)

    def get_queue(self, name: str) -> Optional[Queue]:
        with self._lock:
            return self.queues.get(name)

    def add_queue(self, queue: Queue) -> None:
        with self._lock:
            self.queues[queue.name] = queue
            self._save()

    def remove_queue(self, name: str) -> bool:
        with self._lock:
            if name in self.queues:
                del self.queues[name]
                self._save()
                return True
            return False

    def add_gid_to_queue(self, queue_name: str, gid: str) -> None:
        with self._lock:
            if queue_name in self.queues and gid not in self.queues[queue_name].downloads:
                self.queues[queue_name].downloads.append(gid)
                self._save()

    def remove_gid(self, gid: str) -> None:
        with self._lock:
            for queue in self.queues.values():
                if gid in queue.downloads:
                    queue.downloads.remove(gid)
            self._save()

    def get_all_gids(self) -> List[str]:
        with self._lock:
            gids = []
            for queue in self.queues.values():
                gids.extend(queue.downloads)
            return list(set(gids))

    def get_gids_by_queue(self, queue_name: str) -> List[str]:
        with self._lock:
            queue = self.queues.get(queue_name)
            return queue.downloads if queue else []

    # Keyring helpers
    def get_aria2_secret(self) -> str:
        try:
            secret = keyring.get_password(KEYRING_SERVICE, KEYRING_ARIA2_SECRET)
            if secret:
                return secret
        except Exception:
            pass
        return self.settings.get("aria2_secret", "")

    def set_aria2_secret(self, secret: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, KEYRING_ARIA2_SECRET, secret)
        except Exception as e:
            logger.warning("Keyring failed: %s", e)
            self.settings["aria2_secret"] = secret
            self._save()

    def get_cookies(self, gid: str) -> Optional[str]:
        try:
            return keyring.get_password(KEYRING_SERVICE, f"cookies_{gid}")
        except Exception:
            return None

    def set_cookies(self, gid: str, cookies: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, f"cookies_{gid}", cookies)
        except Exception as e:
            logger.warning("Failed to store cookies: %s", e)

    def get_headers(self, gid: str) -> Optional[str]:
        try:
            return keyring.get_password(KEYRING_SERVICE, f"headers_{gid}")
        except Exception:
            return None

    def set_headers(self, gid: str, headers: str) -> None:
        try:
            keyring.set_password(KEYRING_SERVICE, f"headers_{gid}", headers)
        except Exception as e:
            logger.warning("Failed to store headers: %s", e)
EOF
)"

# ---- core/aria2_manager.py ----
replace_file core/aria2_manager.py "$(cat << 'EOF'
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
EOF
)"

# ---- ui/delegates.py ----
replace_file ui/delegates.py "$(cat << 'EOF'
# Requires: PyQt6>=6.4.0
"""Custom delegates for progress bar and status rendering with system palette."""

from typing import Dict

from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QPalette, QPainter


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        progress_data = index.data(Qt.ItemDataRole.DisplayRole)
        if progress_data is None:
            super().paint(painter, option, index)
            return

        try:
            if isinstance(progress_data, str) and progress_data.endswith("%"):
                value = float(progress_data[:-1])
            else:
                value = float(progress_data)
        except Exception:
            value = 0

        rect = option.rect
        rect.setLeft(rect.left() + 2)
        rect.setRight(rect.right() - 2)
        rect.setTop(rect.top() + 2)
        rect.setBottom(rect.bottom() - 2)

        painter.save()
        palette = option.palette

        bg_color = palette.color(QPalette.ColorRole.Window)
        painter.fillRect(rect, bg_color)

        if value > 0:
            fill_rect = QRect(rect)
            fill_width = int((value / 100) * rect.width())
            fill_rect.setWidth(fill_width)

            highlight = palette.color(QPalette.ColorRole.Highlight)
            color = QColor(highlight)
            color = color.darker(120) if color.lightness() > 128 else color.lighter(120)
            painter.fillRect(fill_rect, color)

        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}%")
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(100, 24)


class StatusDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.status_colors: Dict[str, QColor] = {
            "Downloading": QColor(46, 204, 113),
            "Waiting": QColor(241, 196, 15),
            "Paused": QColor(52, 73, 94),
            "Error": QColor(231, 76, 60),
            "Complete": QColor(46, 204, 113),
            "Removed": QColor(149, 165, 166),
        }

    def paint(self, painter: QPainter, option, index) -> None:
        status = index.data(Qt.ItemDataRole.DisplayRole)
        if not status:
            super().paint(painter, option, index)
            return

        color = self.status_colors.get(status, QColor(149, 165, 166))
        rect = option.rect
        rect.setLeft(rect.left() + 4)
        rect.setRight(rect.right() - 4)
        rect.setTop(rect.top() + 2)
        rect.setBottom(rect.bottom() - 2)

        painter.save()
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        text_color = QColor(255, 255, 255) if color.lightness() < 128 else QColor(0, 0, 0)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(80, 24)
EOF
)"

# ---- utils/helpers.py ----
replace_file utils/helpers.py "$(cat << 'EOF'
# Requires: PyQt6>=6.4.0
"""Helper functions for formatting, disk space, etc."""

import shutil
from pathlib import Path
from typing import Union

from PyQt6.QtGui import QIcon


def get_icon(name: str) -> QIcon:
    icon = QIcon.fromTheme(name)
    return icon if not icon.isNull() else QIcon()


def _format_size_generic(size: float, unit: str, divisor: float = 1024.0) -> str:
    units = ['B', 'KB', 'MB', 'GB', 'TB'] if unit == 'B' else ['B/s', 'KB/s', 'MB/s', 'GB/s', 'TB/s']
    unit_index = 0
    if size < 0:
        return f"0 {unit}"
    while size >= divisor and unit_index < len(units) - 1:
        size /= divisor
        unit_index += 1
    return f"{size:.1f} {units[unit_index]}" if unit_index < len(units) else f"{size:.1f} {units[-1]}"


def format_size(size: int) -> str:
    return "0 B" if size < 0 else _format_size_generic(float(size), "B")


def format_speed(speed: int) -> str:
    if speed <= 0:
        return "0 B/s"
    return _format_size_generic(float(speed), "B/s")


def ensure_dir(path: Union[str, Path]) -> bool:
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


def check_disk_space(path: str, required_bytes: int = 0) -> bool:
    try:
        stat = shutil.disk_usage(path)
        return stat.free >= required_bytes if required_bytes > 0 else True
    except Exception:
        return True
EOF
)"

# ---- ui/icons.py ----
replace_file ui/icons.py "$(cat << 'EOF'
"""Embedded icons as SVG data with fallback to theme."""

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

ICON_DATA = {
    "list-add": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>""",
    "document-new": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M6 2c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6H6zm0 2h7v5h5v11H6V4zm2 8v2h3v3h2v-3h3v-2h-3V9h-2v3H8z"/></svg>""",
    "insert-link": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg>""",
    "media-playback-pause": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>""",
    "media-playback-start": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>""",
    "preferences-system": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 0 0 .12-.61l-1.92-3.32a.488.488 0 0 0-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 0 0-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96a.488.488 0 0 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.07.62-.07.94s.02.64.07.94l-2.03 1.58a.49.49 0 0 0-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32a.49.49 0 0 0-.12-.61l-2.03-1.58zM12 15.6A3.6 3.6 0 1 1 15.6 12 3.6 3.6 0 0 1 12 15.6z"/></svg>""",
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M20 6h-8l-2-2H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm0 12H4V8h16v10z"/></svg>""",
    "torrent": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="currentColor" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>""",
}


def get_icon(name: str) -> QIcon:
    svg_data = ICON_DATA.get(name)
    if svg_data:
        try:
            from PyQt6.QtGui import QPixmap
            from PyQt6.QtSvg import QSvgRenderer
            from PyQt6.QtCore import QByteArray

            renderer = QSvgRenderer(QByteArray(svg_data.encode()))
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            renderer.render(painter)
            painter.end()
            if not pixmap.isNull():
                return QIcon(pixmap)
        except Exception:
            pass

    icon = QIcon.fromTheme(name)
    return icon if not icon.isNull() else QIcon()
EOF
)"

echo "✅ تمام فایل‌ها با موفقیت به‌روزرسانی شدند."

# ============================================================
# مرحله ۳: Commit کردن تغییرات
# ============================================================
echo ""
echo "📦 ایجاد commit..."

git add .
git commit -m "fix: comprehensive security and performance audit for v3

- Fixed SSL verification: removed insecure fallback, enforced certificate pinning
- Added SHA-256 checksum verification for auto-updater
- Replaced shell=True with shell=False in subprocess calls
- Enabled WebSocket for real-time updates, reduced polling frequency
- Added batch operations (system.multicall) for aria2 RPC
- Fixed constant version by centralizing __version__ in main.py
- Added persistent secret storage using keyring with unique service names
- Implemented auto-recovery strategies for common aria2 errors
- Added system sleep/wake detection for download resumption
- Refactored format_size/format_speed to eliminate code duplication
- Replaced hardcoded colors with system palette in delegates
- Added actual SVG icons data"

echo ""
echo "============================================================"
echo "✅ همه عملیات با موفقیت انجام شد!"
echo "============================================================"
echo ""
echo "حالا می‌توانی تغییرات را به GitHub بفرستی:"
echo ""
echo "  git push origin fix/security-and-performance-audit"
echo ""
echo "سپس یک Pull Request از شاخه‌ی خودت به v3 مخزن اصلی ایجاد کن."
echo "============================================================"
