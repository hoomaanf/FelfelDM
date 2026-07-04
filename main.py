#!/usr/bin/env python3
"""
FelfelDM - Download Manager
"""
import sys
import signal
import os
import argparse
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer
from ui.main_window import MainWindow
from utils.style import setup_style, CustomProxyStyle

def signal_handler(sig, frame):
    print("\nForce exit...")
    sys.exit(0)

def main():
    parser = argparse.ArgumentParser(description="FelfelDM - Download Manager")
    parser.add_argument("--add", nargs="+", help="Add URLs to download")
    parser.add_argument("--clear", action="store_true", help="Clear all data")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (no GUI)")
    args = parser.parse_args()
    
    if args.clear:
        import shutil
        config_dir = os.path.expanduser("~/.config/felfelDM")
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
            print("✅ Data cleared!")
        return
    
    # 🔥 حالت Daemon - فقط سرور HTTP
    if args.daemon:
        print("🌶️ FelfelDM Daemon starting...")
        
        # ⭐ نیاز به QApplication برای event loop
        app = QApplication(sys.argv)
        
        from core.local_server import LocalServer
        server = LocalServer()
        server.start(8765)
        
        # اجرای event loop
        sys.exit(app.exec())
        return
    
    # Normal GUI mode
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")
    
    app = QApplication(sys.argv)
    
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Icon
    icon_paths = [
        os.path.join(base_path, "logo/icon256.png"),
        os.path.join(base_path, "logo/icon128.png")
    ]
    icon_set = False
    for path in icon_paths:
        if os.path.exists(path):
            app.setWindowIcon(QIcon(path))
            icon_set = True
            print(f"✅ Icon loaded from: {path}")
            break
    if not icon_set:
        print("⚠️ No icon found! Using default.")

    app.setStyle(CustomProxyStyle())
    app.setApplicationName("FelfelDM")
    app.setQuitOnLastWindowClosed(False)

    win = MainWindow()
    theme = win.store.settings.get("theme", "auto")
    setup_style(app, theme)
    win.show()
    
    if args.add and len(args.add) > 0:
        urls = args.add
        print(f"📥 Adding {len(urls)} URL(s)...")
        QTimer.singleShot(1000, lambda: win._add_downloads_from_extension(urls))
    
    sys.exit(app.exec())


if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()