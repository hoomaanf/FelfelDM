# utils/helpers.py

from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt

def format_size(b):
    b = int(b)
    for u in ["B", "KB", "MB", "GB"]:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def format_speed(b):
    return f"{format_size(b)}/s"

def format_eta(total, completed, speed):
    speed = int(speed)
    if speed <= 0: return "—"
    remaining = int(total) - int(completed)
    if remaining <= 0: return "0s"
    secs = remaining // speed
    if secs < 60: return f"{secs}s"
    if secs < 3600: return f"{secs//60}m {secs%60}s"
    return f"{secs//3600}h {(secs%3600)//60}m"

def get_category(filename):
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    if ext in ['mp4', 'mkv', 'avi', 'flv', 'mov']: return '🎬 Video'
    if ext in ['mp3', 'wav', 'flac', 'm4a', 'aac']: return '🎵 Audio'
    if ext in ['zip', 'rar', '7z', 'tar', 'gz']: return '📦 Archive'
    if ext in ['pdf', 'epub', 'docx', 'txt', 'xlsx']: return '📄 Document'
    if ext in ['iso', 'img']: return '💿 Image'
    return '📁 Other'

def get_icon(name, fallback=None):
    """گرفتن آیکون از تم فعلی با fallback"""
    icon = QIcon.fromTheme(name)
    if icon.isNull() and fallback:
        icon = QIcon.fromTheme(fallback)
    # اگر باز هم null بود، یک آیکون خالی برگردون
    if icon.isNull():
        icon = QIcon()
    return icon