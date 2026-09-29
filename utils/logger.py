# utils/logger.py

import os
import sys
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler


LOG_DIR = Path(os.path.expanduser("~/.cache/felfelDM/logs"))
LOG_FILE = LOG_DIR / "app.log"

_configured = False


def setup_logging():
    """Route every print()/log call to both stdout and a rotating log file.

    Called once from main.py. Idempotent — safe to call multiple times.
    """
    global _configured
    if _configured:
        return
    _configured = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # File handler with rotation: 2 MB per file, keep 3 backups
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    file_handler.setLevel(logging.DEBUG)

    # Stream handler for stdout (what the user sees in the terminal)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter("%(message)s"))
    stream_handler.setLevel(logging.DEBUG)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Avoid duplicate handlers on re-setup
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # Redirect stdout/stderr prints into the logger too, so existing
    # print() calls in the codebase end up in the log file without
    # needing to touch every call site.
    _redirect_std_streams()


class _LoggerWriter:
    """File-like wrapper that forwards .write() to the logger."""

    def __init__(self, logger, level):
        self._logger = logger
        self._level = level
        self._buffer = ""

    def write(self, msg):
        if not msg:
            return
        self._buffer += msg
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line)

    def flush(self):
        if self._buffer.strip():
            self._logger.log(self._level, self._buffer)
        self._buffer = ""


def _redirect_std_streams():
    """Send print() and uncaught tracebacks to the log file too."""
    logger = logging.getLogger("felfelDM.stdout")
    sys.stdout = _LoggerWriter(logger, logging.INFO)
    sys.stderr = _LoggerWriter(logger, logging.ERROR)


def get_log_file_path() -> Path:
    return LOG_FILE