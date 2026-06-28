# core/local_server.py
import json
import logging
import secrets
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QThread, pyqtSignal

logger = logging.getLogger(__name__)


class ServerWorker(QObject):
    """Worker for handling HTTP server requests in a separate thread."""
    urls_received = pyqtSignal(list)

    def __init__(self, port: int = 8765, token: str = ""):
        super().__init__()
        self.port = port
        self.token = token
        self.server = None
        self.running = False

    def start_server(self) -> bool:
        """Start the HTTP server with authentication and CORS restrictions."""
        try:
            # Check if port is available
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', self.port))
            sock.close()
            if result == 0:
                logger.warning(f"Port {self.port} already in use")
                return False

            # Create handler with token and validation
            handler = self._create_handler()
            self.server = HTTPServer(('localhost', self.port), handler)
            self.server.server_worker = self
            self.running = True
            logger.info(f"Local server running on http://localhost:{self.port}")
            while self.running:
                try:
                    self.server.handle_request()
                except Exception as e:
                    if self.running:
                        logger.error(f"Server error: {e}")
                    break
            return True
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    def _create_handler(self):
        """Create a request handler class with authentication and validation."""
        token = self.token

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self.send_response(200)
                # Restrict CORS to localhost only
                self.send_header('Access-Control-Allow-Origin', 'http://localhost')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Auth-Token')
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.end_headers()

            def do_GET(self):
                if self.path == '/ping':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', 'http://localhost')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok"}).encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == '/add':
                    try:
                        # Validate authentication token
                        auth_header = self.headers.get('X-Auth-Token')
                        if not auth_header or auth_header != token:
                            self.send_response(401)
                            self.send_header('Content-Type', 'application/json')
                            self.send_header('Access-Control-Allow-Origin', 'http://localhost')
                            self.end_headers()
                            self.wfile.write(json.dumps({"error": "Unauthorized"}).encode())
                            return

                        length = int(self.headers.get('Content-Length', 0))
                        data = json.loads(self.rfile.read(length).decode())
                        urls = data.get('urls', [])

                        # Validate URLs
                        valid_urls = []
                        for url in urls:
                            parsed = urlparse(url)
                            if parsed.scheme in ('http', 'https', 'ftp', 'magnet'):
                                valid_urls.append(url)
                            else:
                                logger.warning(f"Invalid URL rejected: {url}")

                        if valid_urls and hasattr(self.server, 'server_worker'):
                            self.server.server_worker.urls_received.emit(valid_urls)

                        self.send_response(200)
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', 'http://localhost')
                        self.end_headers()
                        self.wfile.write(json.dumps({
                            "status": "success",
                            "added": len(valid_urls),
                            "rejected": len(urls) - len(valid_urls)
                        }).encode())
                    except Exception as e:
                        logger.error(f"POST error: {e}")
                        self.send_response(500)
                        self.end_headers()
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format: str, *args) -> None:
                """Log HTTP requests using logging.debug."""
                logger.debug(f"HTTP: {format % args}")

        return Handler

    def stop_server(self) -> None:
        """Stop the HTTP server."""
        self.running = False
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None
        logger.info("Server stopped")


class LocalServer:
    """Manager for the local HTTP server with authentication."""

    def __init__(self, callback=None):
        self.callback = callback
        self.thread = None
        self.worker = None
        self.token = secrets.token_urlsafe(32)

    def start(self, port: int = 8765) -> bool:
        """Start the server in a separate thread."""
        if self.thread and self.thread.isRunning():
            return True

        self.thread = QThread()
        self.worker = ServerWorker(port, self.token)
        self.worker.moveToThread(self.thread)
        if self.callback:
            self.worker.urls_received.connect(self.callback)

        self.thread.started.connect(self.worker.start_server)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()
        return True

    def stop(self) -> None:
        """Stop the server."""
        if self.worker:
            self.worker.stop_server()
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self.thread is not None and self.thread.isRunning()

    def get_token(self) -> str:
        """Get the authentication token."""
        return self.token
