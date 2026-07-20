# utils/helpers.py

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
import sys
import os


def format_size(b):
    b = int(b)
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


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
