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
import subprocess
import shutil
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, QTimer, QCoreApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ui.main_window.window import MainWindow
from utils.style import setup_style, CustomProxyStyle
from utils.logger import setup_logging

setup_logging()
import traceback as _traceback


def _global_excepthook(exc_type, exc_value, exc_tb):
    print("\n" + "=" * 70, flush=True)
    print("🚨 UNHANDLED PYTHON EXCEPTION", flush=True)
    print("=" * 70, flush=True)
    _traceback.print_exception(exc_type, exc_value, exc_tb)
    print("=" * 70 + "\n", flush=True)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _global_excepthook
# Global reference for cleanup
server = None
app = None
local_server = None

APP_ID = f"FelfelDM_{os.getenv('USER', 'default')}"

# Do not force DISPLAY: hard-defaulting it to :0 breaks multi-seat, remote
# and `ssh -X` sessions. Qt falls back to the ambient DISPLAY/WAYLAND_DISPLAY.


def signal_handler(sig, frame):
    """Handle SIGINT and SIGTERM signals"""
    print("\n🛑 Received signal, shutting down...")
    global server
    if server:
        try:
            server.stop()
            print("✅ Server stopped")
        except:
            pass

    global local_server
    if local_server:
        try:
            local_server.close()
            QLocalServer.removeServer(APP_ID)
        except:
            pass

    # The normal quit path (MainWindow.quit_app) is skipped on a signal, and
    # aria2 used to keep running afterwards.
    try:
        from core import aria2_process

        aria2_process.stop()
    except Exception:
        pass

    global app
    if app:
        try:
            app.quit()
        except:
            pass

    def force_exit():
        print("⏰ Force exiting...")
        sys.exit(0)

    timer = threading.Timer(2.0, force_exit)
    timer.daemon = True
    timer.start()


def update_self():
    """Update FelfelDM from GitHub using install.sh"""
    print("🔄 Updating FelfelDM from GitHub...")
    print(
        "📥 Running: bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh)"
    )
    print("")

    try:
        result = subprocess.run(
            [
                "bash",
                "-c",
                "curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh | bash",
            ],
            capture_output=False,
            text=True,
        )

        if result.returncode == 0:
            print("")
            print("✅ Update completed successfully!")
            return True
        else:
            print("")
            print(f"❌ Update failed with code: {result.returncode}")
            return False

    except FileNotFoundError:
        print("❌ Error: curl or bash not found. Please install them first.")
        return False
    except Exception as e:
        print(f"❌ Update error: {e}")
        return False


def main():
    global server, app, local_server

    parser = argparse.ArgumentParser(description="FelfelDM - Download Manager")
    parser.add_argument("--add", nargs="+", help="Add URLs to download")
    parser.add_argument("--clear", action="store_true", help="Clear all data")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (no GUI)")
    parser.add_argument(
        "--update", action="store_true", help="Update FelfelDM from GitHub"
    )
    parser.add_argument("--youtube-url", type=str, default=None)
    args = parser.parse_args()

    if args.update:
        print("🌶️ FelfelDM Updater")
        print("=" * 50)
        if update_self():
            print("=" * 50)
            print("✅ Update successful! Please restart FelfelDM.")
            print("💡 Run: FelfelDM")
        else:
            print("=" * 50)
            print(
                "❌ Update failed! Please check your internet connection and try again."
            )
            print(
                "💡 Or manually run: bash <(curl -s https://raw.githubusercontent.com/hoomaanf/FelfelDM/main/install.sh)"
            )
        return

    if args.clear:
        config_dir = os.path.expanduser("~/.config/felfelDM")
        if os.path.exists(config_dir):
            shutil.rmtree(config_dir)
            print("✅ Data cleared!")
        return

    if args.daemon:
        print("🌶️ FelfelDM Daemon starting...")
        from core.local_server import LocalServer

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

    if args.add or getattr(args, "youtube_url", None):
        import json as _json
        import urllib.request as _urllib_request

        _forwarded = False

        for _port in (8766, 8765):
            try:
                with _urllib_request.urlopen(
                    f"http://127.0.0.1:{_port}/ping", timeout=1
                ):
                    pass
            except Exception:
                continue

            print(f"📥 Forwarding to running FelfelDM on port {_port}...")

            if args.add:
                for _url in args.add:
                    try:
                        _req = _urllib_request.Request(
                            f"http://127.0.0.1:{_port}/add",
                            data=_json.dumps({"url": _url}).encode("utf-8"),
                            headers={"Content-Type": "application/json"},
                            method="POST",
                        )
                        with _urllib_request.urlopen(_req, timeout=5):
                            print(f"  ✅ {_url}")
                    except Exception as _e:
                        print(f"  ⚠️ {_url}: {_e}")

            if getattr(args, "youtube_url", None):
                try:
                    _req = _urllib_request.Request(
                        f"http://127.0.0.1:{_port}/open",
                        data=_json.dumps(
                            {"url": args.youtube_url, "kind": "youtube"}
                        ).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with _urllib_request.urlopen(_req, timeout=5):
                        print(f"✅ YouTube dialog requested: {args.youtube_url}")
                except Exception as _e:
                    print(f"⚠️ {_e}")

            _forwarded = True
            break

        if _forwarded:
            return

        # Nothing was listening. If we're headless, launching the GUI
        # would just abort again — fail with a clear message instead.
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            print(
                "❌ FelfelDM is not running and no display is available.\n"
                "   Start it with one of:\n"
                "     FelfelDM                                 # GUI\n"
                "     systemctl --user start felfeldm.service  # daemon",
                file=sys.stderr,
            )
            sys.exit(1)

    # Normal GUI mode
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    # Prefer the Wayland plugin only when a Wayland session actually exists;
    # otherwise Qt would fail to open a window on an X11-only system instead
    # of falling back to xcb.
    if os.environ.get("WAYLAND_DISPLAY"):
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
            break
    if not icon_set:
        print("⚠️ No icon found! Using default.")

    app.setStyle(CustomProxyStyle())
    app.setApplicationName("FelfelDM")
    app.setQuitOnLastWindowClosed(False)

    win = MainWindow()
    theme = win.store.settings.get("theme", "auto")
    setup_style(app, theme)

    # Detect if this launch is triggered by the browser extension
    is_extension_launch = bool(args.add and len(args.add) > 0)

    if not is_extension_launch:
        win.show()

    if is_extension_launch:
        urls = args.add
        print(f"📥 Adding {len(urls)} URL(s)...")
        QTimer.singleShot(1000, lambda: win._add_from_extension(urls))

    # ── Handle --youtube-url (from daemon / browser extension) ──
    if getattr(args, "youtube_url", None):
        yt_url = args.youtube_url
        print(f"📥 Opening YouTube dialog for: {yt_url}")
        # Show the window (since is_extension_launch is False, it was shown
        # already, but ensure it is visible and on top).
        win.show()
        win.raise_()
        win.activateWindow()
        # Delay slightly so the window and its dialogs are fully initialised.
        QTimer.singleShot(800, lambda: win._open_youtube_dialog_with_url(yt_url))

        # Do NOT exit via sys.exit(app.exec()) twice — just let the event
        # loop continue; the timer will fire and open the dialog.

    sys.exit(app.exec())


if __name__ == "__main__":
    # Default signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    main()
