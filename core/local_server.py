# core/local_server.py
"""
Local HTTP server for browser extension integration with token authentication.
"""

import json
import logging
import secrets
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class LocalServer(QObject):
    """
    Local HTTP server that receives URLs from the browser extension.
    Uses token-based authentication with constant-time comparison.
    """

    urls_received = pyqtSignal(list)

    def __init__(self, download_controller, port: int = 8080) -> None:
        super().__init__()
        self.download_controller = download_controller
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._token = secrets.token_urlsafe(32)

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        if self._running:
            return

        self._running = True
        self._server = HTTPServer(("localhost", self.port), self._create_handler())
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Local server started on port %d", self.port)

    def _run(self) -> None:
        """Run the server loop."""
        while self._running:
            try:
                self._server.handle_request()
            except Exception as e:
                logger.error("Local server error: %s", e)

    def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=1)
        logger.info("Local server stopped")

    def get_token(self) -> str:
        """Get the authentication token for the browser extension."""
        return self._token

    def _create_handler(self):
        """Create a request handler class with access to this instance."""
        handler = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._handle_request()

            def do_POST(self):
                self._handle_request()

            def do_OPTIONS(self):
                self._handle_options()

            def _handle_options(self):
                """Handle CORS preflight requests."""
                self.send_response(200)
                self._send_cors_headers()
                self.end_headers()

            def _send_cors_headers(self):
                """Send CORS headers."""
                self.send_header("Access-Control-Allow-Origin", "http://localhost")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "X-Auth-Token, Content-Type")
                self.send_header("Access-Control-Max-Age", "86400")

            def _handle_request(self):
                # CORS headers
                self._send_cors_headers()
                self.end_headers()

                # Handle OPTIONS preflight
                if self.command == "OPTIONS":
                    return

                # Verify token with constant-time comparison
                token_header = self.headers.get("X-Auth-Token", "")
                if not token_header:
                    self.wfile.write(b'{"error": "Missing token"}')
                    return

                if not secrets.compare_digest(token_header, handler._token):
                    self.wfile.write(b'{"error": "Invalid token"}')
                    return

                # Handle GET requests - no token in response
                if self.command == "GET":
                    self.wfile.write(b'{"status": "ok"}')
                    return

                # Handle POST requests
                if self.command == "POST":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length).decode("utf-8")
                    try:
                        data = json.loads(body)
                        urls = data.get("urls", [])
                        if urls:
                            handler.urls_received.emit(urls)
                            self.wfile.write(f'{{"status": "ok", "count": {len(urls)}}}'.encode())
                        else:
                            self.wfile.write(b'{"error": "No URLs provided"}')
                    except json.JSONDecodeError:
                        self.wfile.write(b'{"error": "Invalid JSON"}')

            def log_message(self, format, *args):
                # Suppress default logging
                pass

        return Handler
