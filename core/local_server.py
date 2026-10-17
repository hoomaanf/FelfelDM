# core/local_server.py

import json
import socket
import subprocess
import os
import threading
from typing import Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from PyQt6.QtCore import QThread, pyqtSignal

# Only the browser extension itself is allowed to call this server
# cross-origin. Echoing "*" back let ANY website the user has open in a
# tab silently POST to /add via fetch() and queue arbitrary downloads.
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")

# Hard cap on request bodies. The URL list we accept is tiny; an unbounded
# Content-Length let a single request allocate arbitrary memory.
MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MiB

# Bodies up to this size are drained (so the kept-alive connection stays
# usable) when a request is rejected before being read. Anything larger
# causes the connection to be closed instead.
MAX_DRAIN_BYTES = 64 * 1024

# A client that opens a connection and never finishes sending its request
# must not be able to occupy a handler forever.
REQUEST_TIMEOUT_SECONDS = 10

# Upper bound on how many URLs one request may enqueue.
MAX_URLS_PER_REQUEST = 500


def _cors_origin(headers) -> Optional[str]:
    origin = headers.get("Origin")
    if origin and origin.startswith(ALLOWED_ORIGIN_PREFIXES):
        return origin
    return None


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded server so one slow/stalled client cannot block the rest.

    HTTPServer handles requests serially: a single connection that opens
    but never sends its body would wedge /ping and /add for every other
    caller. daemon_threads also lets the process exit without waiting on
    stray handler threads.
    """

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32


class ServerThread(QThread):
    urls_received = pyqtSignal(list)
    # Emitted once the listening socket is bound (or binding failed), for
    # any listener that wants to react. Callers that must *block* until the
    # server is up use wait_until_ready() instead: a Qt signal cannot be
    # delivered while the waiting thread is inside a blocking wait().
    ready = pyqtSignal(bool)

    def __init__(self, port=8765, main_window=None):
        super().__init__()
        self.port = port
        self.main_window = main_window
        self.server = None
        self.running = False
        # Separate from `running`: run() sets `running = True` once binding
        # succeeds, so a stop() that arrives before the thread starts would
        # be overwritten and the loop would come up anyway. This flag is
        # only ever cleared by stop().
        self._stop_requested = False
        # Set when run() has finished binding (successfully or not).
        self._ready_event = threading.Event()
        self._bind_ok = False

    def wait_until_ready(self, timeout: float = 5.0) -> bool:
        """Block until binding is done. Returns whether the port is bound.

        Uses a threading.Event rather than the `ready` signal so it works
        even when the calling thread is not spinning an event loop.
        """
        if not self._ready_event.wait(timeout):
            return False
        return self._bind_ok

    def _mark_ready(self, ok: bool) -> None:
        self._bind_ok = ok
        self._ready_event.set()
        self.ready.emit(ok)

    def run(self):
        try:
            self.server = _ThreadingHTTPServer(("localhost", self.port), Handler)
            self.server.server_thread = self
            # Bound the accept wait so the loop re-checks the stop flag at
            # least twice a second instead of blocking in accept().
            self.server.timeout = 0.5

            if self._stop_requested:
                # stop() was called before we got here; do not start serving.
                self.server.server_close()
                self.server = None
                self._mark_ready(False)
                return

            self.running = True
            print(f"✅ Local server running on http://localhost:{self.port}")
            self._mark_ready(True)

            # A manual handle_request() loop is used (rather than
            # serve_forever()) because it honours server.timeout, which is
            # what makes stop() return promptly. server.shutdown() must NOT
            # be used here: it waits on an event that only serve_forever()
            # sets, so calling it would block forever.
            while not self._stop_requested:
                self.server.handle_request()

        except OSError as e:
            print(f"❌ Server failed to bind port {self.port}: {e}")
            self._mark_ready(False)
        except Exception as e:
            if not self._stop_requested:
                print(f"❌ Server failed: {e}")
            self._mark_ready(False)
        finally:
            self.running = False
            # Ensure a caller waiting on readiness is never left hanging if
            # we bailed out before reaching either _mark_ready() call.
            self._ready_event.set()

    def stop(self):
        """Stop the server and release the port.

        Safe to call at any point in the lifecycle, including before the
        thread has finished binding, and from the UI thread.
        """
        self._stop_requested = True
        self.running = False

        # Wait for the loop to leave handle_request() before touching the
        # socket, so it is never closed out from under a blocked accept.
        if not self.wait(5000):
            print("⚠️ Local server thread did not exit in 5s")

        if self.server:
            try:
                self.server.server_close()
            except Exception:
                pass
            self.server = None

        print("🛑 Server stopped")


class Handler(BaseHTTPRequestHandler):

    # Per-connection read timeout, so a stalled client is dropped instead
    # of pinning a handler thread forever.
    timeout = REQUEST_TIMEOUT_SECONDS

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    # ── CORS helpers ──────────────────────────────────────────────

    def _send_cors_headers(self) -> None:
        origin = _cors_origin(self.headers)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send_json(self, status: int, payload: dict, close: bool = False) -> None:
        """Send a JSON response.

        `close=True` is required for any response sent WITHOUT having read
        the request body: the unread bytes would otherwise be parsed as the
        start of the next request on a kept-alive connection (protocol
        desync). Closing the connection discards them.
        """
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if close:
            self.close_connection = True
            self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # Client went away before reading the response.
            self.close_connection = True

    def _drain_or_close(self, length: int) -> None:
        """Consume a request body we are going to reject.

        Drains small bodies so the connection stays usable, and closes the
        connection for large ones rather than reading unbounded data.
        """
        if 0 < length <= MAX_DRAIN_BYTES:
            try:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except (OSError, TimeoutError):
                self.close_connection = True
        else:
            self.close_connection = True

    def _read_json_body(self) -> Optional[dict]:
        """Read and parse the request body, enforcing a hard size cap.

        Returns None when the body is missing, malformed, or too large; a
        response has already been sent in every one of those cases.
        """
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self._send_json(
                400, {"status": "error", "message": "bad content-length"}, close=True
            )
            return None

        if length < 0:
            self._send_json(
                400, {"status": "error", "message": "bad content-length"}, close=True
            )
            return None

        if length > MAX_BODY_BYTES:
            # Do not read the body; just make sure it can't desync the stream.
            self.close_connection = True
            self._send_json(
                413, {"status": "error", "message": "payload too large"}, close=True
            )
            return None

        try:
            raw = self.rfile.read(length) if length else b""
        except (OSError, TimeoutError):
            # Socket is unusable; no response can be delivered.
            self.close_connection = True
            return None

        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(
                400, {"status": "error", "message": "invalid JSON"}
            )
            return None

        if not isinstance(data, dict):
            self._send_json(
                400, {"status": "error", "message": "expected a JSON object"}
            )
            return None

        return data

    # ── HTTP verbs ────────────────────────────────────────────────

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"status": "error", "message": "not found"})

    def do_POST(self):
        if self.path == "/open":
            self._handle_open()
            return
        if self.path != "/add":
            try:
                pending = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                pending = 0
            self._drain_or_close(pending)
            self._send_json(
                404,
                {"status": "error", "message": "not found"},
                close=self.close_connection,
            )
            return

        # A cross-origin POST with a "simple" content-type (e.g.
        # text/plain) skips the CORS preflight entirely, so a malicious
        # page could still get this handler to run even though it can't
        # read the response. Reject any request that carries a
        # browser-set Origin header we don't recognize *before* doing
        # anything with the body. Requests with no Origin header at all
        # (non-browser callers) are left alone.
        origin_header = self.headers.get("Origin")
        if origin_header and not origin_header.startswith(ALLOWED_ORIGIN_PREFIXES):
            print(f"🚫 Rejected /add from disallowed origin: {origin_header}")
            # The body has not been read yet. Drain it (small) or close the
            # connection (large) so the unread bytes can't be mistaken for
            # the next request.
            try:
                pending = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                pending = 0
            self._drain_or_close(pending)
            self._send_json(
                403,
                {"status": "error", "message": "forbidden origin"},
                close=self.close_connection,
            )
            return

        data = self._read_json_body()
        if data is None:
            return

        urls = data.get("urls", [])
        if not isinstance(urls, list):
            self._send_json(400, {"status": "error", "message": "urls must be a list"})
            return

        # Only accept well-formed strings; silently drop anything else so a
        # malformed payload can't reach aria2.
        urls = [u for u in urls if isinstance(u, str) and u.strip()][
            :MAX_URLS_PER_REQUEST
        ]

        if urls:
            print(f"📥 Received {len(urls)} URL(s) on port {self.server.server_port}")
            thread = getattr(self.server, "server_thread", None)
            if thread is not None:
                if thread.main_window:
                    from PyQt6.QtCore import QMetaObject, Qt, Q_ARG

                    QMetaObject.invokeMethod(
                        thread.main_window,
                        "_add_from_extension",
                        Qt.ConnectionType.QueuedConnection,
                        Q_ARG(list, urls),
                    )
                    print(f"✅ Invoked _add_from_extension with {len(urls)} URL(s)")
                else:
                    print(f"🚀 Daemon mode: Launching FelfelDM with {len(urls)} URL(s)")
                    self._launch_with_urls(urls)

        self._send_json(200, {"status": "success", "accepted": len(urls)})

    def _handle_open(self):
        """Handle POST /open: {url, kind}.

        kind is optional; when missing, MainWindow decides based on the URL.
        """
        origin_header = self.headers.get("Origin")
        if origin_header and not origin_header.startswith(ALLOWED_ORIGIN_PREFIXES):
            print(f"🚫 Rejected /open from disallowed origin: {origin_header}")
            try:
                pending = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                pending = 0
            self._drain_or_close(pending)
            self._send_json(
                403,
                {"status": "error", "message": "forbidden origin"},
                close=self.close_connection,
            )
            return

        data = self._read_json_body()
        if data is None:
            return

        url = data.get("url", "")
        if not isinstance(url, str) or not url.strip():
            self._send_json(400, {"status": "error", "message": "url required"})
            return

        kind = data.get("kind", "")
        if kind not in ("youtube", "download", ""):
            kind = ""

        print(f"📥 Received /open: url={url[:80]!r}, kind={kind!r}")

        thread = getattr(self.server, "server_thread", None)
        if thread is not None and thread.main_window:
            from PyQt6.QtCore import QMetaObject, Qt, Q_ARG

            QMetaObject.invokeMethod(
                thread.main_window,
                "_open_dialog_from_extension",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, url),
                Q_ARG(str, kind),
            )
            self._send_json(200, {"status": "success"})
        elif thread is not None:
            # Daemon mode: no GUI to open a dialog in.
            if kind == "youtube":
                print(f"🚀 Daemon mode: launching YouTube dialog for {url!r}")
                self._launch_youtube_dialog(url)
            else:
                print(f"🚀 Daemon mode: queuing {url!r} via --add")
                self._launch_with_urls([url])
            self._send_json(200, {"status": "queued"})
            
    def _launch_youtube_dialog(self, url):
        """Launch FelfelDM with --youtube-url so the YouTube dialog opens."""
        try:
            exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "/usr/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "FelfelDM"

            cmd = [exe_path, "--youtube-url", url]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"✅ Launched YouTube dialog: {' '.join(cmd)}")
        except Exception as e:
            print(f"❌ Failed to launch YouTube dialog: {e}")
    
    def _launch_with_urls(self, urls):
        """Launch FelfelDM with URLs in daemon mode"""
        try:
            exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "/usr/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "FelfelDM"

            cmd = [exe_path, "--add", *urls]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            print(f"✅ Launched: {' '.join(cmd)}")
        except Exception as e:
            print(f"❌ Failed to launch: {e}")


class LocalServer:

    def __init__(self, main_window=None):
        self.main_window = main_window
        self.thread = None

    def start(self, port=8765):
        if self.thread and self.thread.isRunning():
            return True

        # Drop a finished/never-started thread so a restart is clean.
        if self.thread is not None:
            self.thread.stop()
            self.thread = None

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result == 0:
                # Something is already listening. This is the normal case
                # when a previous FelfelDM (or its daemon) is up, so report
                # success rather than starting a second server.
                print(f"⚠️ Port {port} already in use")
                return True

            self.thread = ServerThread(port, self.main_window)

            if self.main_window:
                self.thread.urls_received.connect(
                    self.main_window._add_from_extension
                )

            # Wait for the bind to complete so the port is actually listening (and a
            # failed bind is reported) by the time start() returns.
            self.thread.start()
            return self.thread.wait_until_ready(5.0)

        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False

    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None

    def is_running(self):
        return bool(self.thread and self.thread.isRunning())