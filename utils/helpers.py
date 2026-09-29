# utils/helpers.py

from PyQt6.QtGui import QIcon
import sys
import os


def format_size(b):
    """
    Format a byte count into a human-readable string.

    Handles:
      - None / invalid input
      - Negative values (treats as unsigned 64-bit)
      - Very large values (>2 GiB) without 32-bit overflow
    """
    if b is None:
        return "0 B"

    try:
        b = int(b)
    except (ValueError, TypeError):
        return "0 B"

    # Convert negative to unsigned 64-bit (handles any accidental overflow)
    if b < 0:
        b = b & 0xFFFFFFFFFFFFFFFF

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    idx = 0
    value = float(b)

    while value >= 1024 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1

    # Bytes: no decimal. Larger units: 2 decimal places.
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.2f} {units[idx]}"


def format_speed(b):
    return f"{format_size(b)}/s"


def format_eta(total, completed, speed):
    speed = int(speed)
    if speed <= 0:
        return "—"
    remaining = int(total) - int(completed)
    if remaining <= 0:
        return "0s"
    secs = remaining // speed
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs//60}m {secs%60}s"
    return f"{secs//3600}h {(secs%3600)//60}m"


def get_file_extension(filename: str) -> str:
    if not filename:
        return ""
    filename = filename.split("?")[0]
    filename = filename.split("#")[0]
    filename = os.path.basename(filename)
    ext = os.path.splitext(filename)[1]
    if ext.startswith("."):
        ext = ext[1:]
    return ext.lower()


def get_category_from_extension(ext: str) -> str:
    categories = {
        "🎬 Video": [
            "mp4",
            "mkv",
            "avi",
            "mov",
            "wmv",
            "flv",
            "webm",
            "m4v",
            "3gp",
            "mpg",
            "mpeg",
            "ts",
            "m2ts",
        ],
        "🎵 Audio": [
            "mp3",
            "wav",
            "flac",
            "aac",
            "ogg",
            "m4a",
            "wma",
            "opus",
            "alac",
            "dsd",
        ],
        "📦 Archive": [
            "zip",
            "rar",
            "7z",
            "tar",
            "gz",
            "bz2",
            "xz",
            "iso",
            "img",
            "dmg",
            "cab",
            "arj",
            "lzh",
            "tgz",
            "zst",
        ],
        "📄 Document": [
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "odt",
            "ods",
            "odp",
            "txt",
            "rtf",
            "md",
            "csv",
            "tsv",
        ],
        "🖼️ Image": [
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "svg",
            "webp",
            "ico",
            "tiff",
            "tif",
            "raw",
            "psd",
            "ai",
            "eps",
            "heic",
            "heif",
        ],
        "⚙️ Program": [
            "exe",
            "msi",
            "deb",
            "rpm",
            "apk",
            "app",
            "pkg",
            "sh",
            "bat",
            "cmd",
            "py",
            "jar",
            "war",
            "dmg",
            "flatpak",
        ],
        "💻 Code": [
            "py",
            "js",
            "html",
            "css",
            "php",
            "java",
            "c",
            "cpp",
            "h",
            "go",
            "rs",
            "ts",
            "json",
            "xml",
            "yaml",
            "toml",
            "sql",
            "sh",
            "rb",
            "pl",
            "lua",
            "r",
            "swift",
            "kt",
            "dart",
        ],
        "📚 Ebook": ["epub", "mobi", "azw", "azw3", "fb2", "lit", "lrf", "pdf"],
        "🔤 Font": ["ttf", "otf", "woff", "woff2", "eot", "pfb", "pfm", "fnt"],
        "🗄️ Database": [
            "db",
            "sqlite",
            "sqlite3",
            "mdb",
            "accdb",
            "sql",
            "dump",
            "bak",
        ],
        "💿 Disk": ["iso", "img", "dmg", "vhd", "vmdk", "qcow2", "raw"],
        "🧲 Torrent": ["torrent"],
        "📝 Subtitle": ["srt", "ass", "ssa", "sub", "vtt", "sbv"],
        "📋 Playlist": ["m3u", "m3u8", "pls", "xspf", "wpl"],
    }

    for category, extensions in categories.items():
        if ext in extensions:
            return category

    return "📁 Other"


def get_category_from_filename(filename: str) -> str:
    ext = get_file_extension(filename)
    return get_category_from_extension(ext)


def get_category_icon(category: str) -> str:
    icons = {
        "🎬 Video": "🎬",
        "🎵 Audio": "🎵",
        "📦 Archive": "📦",
        "📄 Document": "📄",
        "🖼️ Image": "🖼️",
        "⚙️ Program": "⚙️",
        "💻 Code": "💻",
        "📚 Ebook": "📚",
        "🔤 Font": "🔤",
        "🗄️ Database": "🗄️",
        "💿 Disk": "💿",
        "🧲 Torrent": "🧲",
        "📝 Subtitle": "📝",
        "📋 Playlist": "📋",
    }
    return icons.get(category, "📁")


def get_category(filename):
    ext = get_file_extension(filename)
    return get_category_from_extension(ext)


def get_icon(name, fallback=None):
    icon = QIcon.fromTheme(name)
    if icon.isNull() and fallback:
        icon = QIcon.fromTheme(fallback)
    if icon.isNull():
        icon = QIcon()
    return icon


def get_resource_path(relative_path):
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    return os.path.join(base_path, relative_path)


def get_error_reason(error_msg: str) -> str:
    """Map a raw aria2 error message to a short human-readable label.

    Only the most common patterns are handled; anything unrecognized
    falls back to a generic "Download failed".
    """
    if not error_msg:
        return "Download failed"

    msg = error_msg.lower()

    # HTTP status codes
    if "404" in msg or "not found" in msg:
        return "404 Not Found"
    if "403" in msg or "forbidden" in msg:
        return "403 Forbidden"
    if "401" in msg or "unauthorized" in msg:
        return "401 Unauthorized"
    if "410" in msg or "gone" in msg:
        return "410 Gone"
    if "451" in msg:
        return "451 Unavailable for Legal Reasons"
    if "429" in msg or "too many requests" in msg:
        return "429 Too Many Requests"
    if "500" in msg or "internal server error" in msg:
        return "500 Server Error"
    if "502" in msg or "bad gateway" in msg:
        return "502 Bad Gateway"
    if "503" in msg or "service unavailable" in msg:
        return "503 Service Unavailable"
    if "504" in msg or "gateway timeout" in msg:
        return "504 Gateway Timeout"

    # TLS / certificate
    if (
        "certificate" in msg
        or "cert verify" in msg
        or "tls" in msg
        or "ssl" in msg
    ):
        return "TLS/Certificate error"

    # DNS
    if (
        "name resolution" in msg
        or "could not resolve" in msg
        or "unable to resolve" in msg
        or "could not contact dns" in msg
        or "dns servers" in msg
    ):
        return "DNS resolution failed"

    # Timeouts
    if "timeout" in msg or "timed out" in msg:
        return "Connection timeout"

    # Connection issues
    if (
        "connection" in msg
        or "reset by peer" in msg
        or "refused" in msg
        or "eof from the server" in msg
        or "got eof" in msg
    ):
        return "Connection error"

    if "no route" in msg or "unreachable" in msg:
        return "Network unreachable"

    return "Download failed"


def get_retry_status(download: dict) -> str:
    """Return a short label describing the current retry state.

    Uses only fields already present on the download dict, so it stays
    in sync with whatever the UI knows at that moment.
    """
    if not download:
        return "—"

    status = download.get("status", "")

    if status == "retrying":
        detail = download.get("status_detail", "")
        # status_detail looks like: "🔄 Retrying in 12s... (2/5)"
        # Extract just the "12s" part if possible.
        import re as _re

        m = _re.search(r"in (\d+)s", detail)
        if m:
            return f"In {m.group(1)}s"
        return "In progress"

    if status in ("active", "downloading"):
        return "—"

    if status == "error":
        return "Not retryable"

    return "—"