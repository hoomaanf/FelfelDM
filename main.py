#!/usr/bin/env python3
"""
FelfelDM - Download Manager
"""
import sys
import signal
import os
import argparse
import threading
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer, QCoreApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ui.main_window import MainWindow
from utils.style import setup_style, CustomProxyStyle

# Global reference for cleanup
server = None
app = None
local_server = None  #

APP_ID = f"FelfelDM_{os.getenv('USER', 'default')}"


def signal_handler(sig, frame):
    """Handle SIGINT and SIGTERM signals"""
    print("\n🛑 Received signal, shutting down...")

    # Stop local server
    global server
    if server:
        try:
            server.stop()
            print("✅ Server stopped")
        except:
            pass

    # Stop QLocalServer
    global local_server
    if local_server:
        try:
            local_server.close()
            QLocalServer.removeServer(APP_ID)
        except:
            pass

    # Quit application
    global app
    if app:
        try:
            app.quit()
        except:
            pass

    # Force exit after 2 seconds
    def force_exit():
        print("⏰ Force exiting...")
        sys.exit(0)

    timer = threading.Timer(2.0, force_exit)
    timer.daemon = True
    timer.start()


def main():
    global server, app, local_server

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

    if args.daemon:
        print("🌶️ FelfelDM Daemon starting...")

        from PyQt6.QtCore import QCoreApplication
        from core.local_server import LocalServer
        import signal
        import time

        app = QCoreApplication(sys.argv)
        server = LocalServer()
        server.start(8765)

        running = True

        def signal_handler(sig, frame):
            global running
            print(f"🛑 Received signal {sig}, shutting down daemon...")
            running = False
            server.stop()
            app.quit()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        while running:
            try:
                time.sleep(0.5)
            except:
                break

        print("Daemon stopped.")
        return

    # Normal GUI mode
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", "kde")

    app = QApplication(sys.argv)

    # ===== Single Instance Check =====
    socket = QLocalSocket()
    socket.connectToServer(APP_ID)

    if socket.waitForConnected(300):
        print("🔄 Another instance is running. Activating existing window...")
        socket.disconnectFromServer()
        sys.exit(0)

    local_server = QLocalServer()
    QLocalServer.removeServer(APP_ID)

    if not local_server.listen(APP_ID):
        print(f"❌ Error: Could not start local server on {APP_ID}")
        sys.exit(1)

    def on_new_connection():
        client_socket = local_server.nextPendingConnection()
        if client_socket:
            if win:
                win.show()
                win.raise_()
                win.activateWindow()
            client_socket.disconnectFromServer()

    local_server.newConnection.connect(on_new_connection)

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Icon
    icon_paths = [
        os.path.join(base_path, "logo/icon512.png"),
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
    # Default signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()
