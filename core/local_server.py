# core/local_server.py

import json
import socket
import subprocess
import os
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from PyQt6.QtCore import QThread, pyqtSignal

# Only the browser extension itself is allowed to call this server
# cross-origin. Echoing "*" back let ANY website the user has open in a
# tab silently POST to /add via fetch() and queue arbitrary downloads.
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")


def _cors_origin(headers) -> Optional[str]:
    origin = headers.get("Origin")
    if origin and origin.startswith(ALLOWED_ORIGIN_PREFIXES):
        return origin
    return None


class ServerThread(QThread):
    urls_received = pyqtSignal(list)

    def __init__(self, port=8765, main_window=None):
        super().__init__()
        self.port = port
        self.main_window = main_window
        self.server = None
        self.running = False

    def run(self):
        try:
            self.server = HTTPServer(("localhost", self.port), Handler)
            self.server.server_thread = self
            self.running = True
            print(f"✅ Local server running on http://localhost:{self.port}")

            while self.running:
                try:
                    self.server.handle_request()
                except Exception as e:
                    if self.running:
                        print(f"Server error: {e}")
                    break

        except Exception as e:
            print(f"❌ Server failed: {e}")

    def stop(self):
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except:
                pass
        self.quit()
        self.wait()
        print("🛑 Server stopped")


class Handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        origin = _cors_origin(self.headers)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            origin = _cors_origin(self.headers)
            if origin:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/add":
            # A cross-origin POST with a "simple" content-type (e.g.
            # text/plain) skips the CORS preflight entirely, so a
            # malicious page could still get this handler to run even
            # though it can't read the response. Reject any request that
            # carries a browser-set Origin header we don't recognize
            # *before* doing anything with the body. Requests with no
            # Origin header at all (non-browser callers) are left alone.
            origin_header = self.headers.get("Origin")
            if origin_header and not origin_header.startswith(ALLOWED_ORIGIN_PREFIXES):
                print(f"🚫 Rejected /add from disallowed origin: {origin_header}")
                self.send_response(403)
                self.end_headers()
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(length).decode())
                urls = data.get("urls", [])

                print(
                    f"📥 Received {len(urls)} URL(s) on port {self.server.server_port}"
                )

                if urls and hasattr(self.server, "server_thread"):
                    thread = self.server.server_thread
                    if thread.main_window:
                        from PyQt6.QtCore import QMetaObject, Qt, Q_ARG

                        QMetaObject.invokeMethod(
                            thread.main_window,
                            "_add_from_extension",
                            Qt.ConnectionType.QueuedConnection,
                            Q_ARG(list, urls),
                        )
                        print(
                            f"✅ Invoked _add_from_extension with {len(urls)} URL(s)"
                        )
                    else:
                        print(
                            f"🚀 Daemon mode: Launching FelfelDM with {len(urls)} URL(s)"
                        )
                        self._launch_with_urls(urls)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                origin = _cors_origin(self.headers)
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode())

            except Exception as e:
                print(f"❌ POST error: {e}")
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _launch_with_urls(self, urls):
        """Launch FelfelDM with URLs in daemon mode"""
        try:
            exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "FelfelDM"

            cmd = [exe_path, "--add"] + urls
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"✅ Launched: {' '.join(cmd)}")
        except Exception as e:
            print(f"❌ Failed to launch: {e}")

    def log_message(self, *args):
        pass


class LocalServer:

    def __init__(self, main_window=None):
        self.main_window = main_window
        self.thread = None

    def start(self, port=8765):
        if self.thread and self.thread.isRunning():
            return True

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result == 0:
                print(f"⚠️ Port {port} already in use")
                return True

            self.thread = ServerThread(port, self.main_window)

            if self.main_window:
                self.thread.urls_received.connect(
                    self.main_window._add_from_extension
                )

            self.thread.start()
            return True

        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False

    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None

    def is_running(self):
        return self.thread and self.thread.isRunning()