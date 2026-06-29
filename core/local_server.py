# =============================================================================
# core/local_server.py
# =============================================================================
import json
import secrets
import logging
import socket
from pathlib import Path
from typing import Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

logger = logging.getLogger(__name__)

TOKEN_DIR = Path.home() / ".felfeldm"
TOKEN_FILE = TOKEN_DIR / "token.json"


class TokenManager:
    """Manage persistent token for browser extension communication."""

    @staticmethod
    def get_or_create_token() -> str:
        """Retrieve existing token or create a new one and persist it."""
        try:
            TOKEN_DIR.mkdir(parents=True, exist_ok=True)
            if TOKEN_FILE.exists():
                with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("token")
                    if token and isinstance(token, str) and len(token) >= 16:
                        return token
        except Exception as e:
            logger.warning("Failed to read token: %s", e)

        token = secrets.token_urlsafe(32)
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": token}, f, indent=2)
            TOKEN_FILE.chmod(0o600)
        except Exception as e:
            logger.error("Failed to save token: %s", e)
        return token


class LocalServerHandler(BaseHTTPRequestHandler):
    token: str = ""

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/token":
            self.send_error(404, "Not found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        provided_token = query.get("token", [None])[0]
        if provided_token != self.token:
            self.send_error(401, "Unauthorized")
            return

        response = {
            "host": self.server.server_address[0],
            "port": self.server.server_address[1],
            "secret": self.token,
            "protocol": "http"
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        pass


class LocalServer:
    """HTTP server for browser extension integration with port fallback."""

    def __init__(self, host: str = "127.0.0.1", port: Optional[int] = None):
        self.host = host
        self.port = port or self._get_default_port()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.token = TokenManager.get_or_create_token()

    @staticmethod
    def _get_default_port() -> int:
        """Get port from config or default to 8080."""
        config_file = Path.home() / ".felfeldm" / "local_server_config.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    port = data.get("port")
                    if port and isinstance(port, int):
                        return port
            except Exception:
                pass
        return 8080

    def _find_available_port(self, start_port: int, max_tries: int = 10) -> Optional[int]:
        """Try to find an available port starting from start_port."""
        for port in range(start_port, start_port + max_tries):
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.bind((self.host, port))
                test_sock.close()
                return port
            except OSError:
                continue
        return None

    def start(self) -> bool:
        """Start the HTTP server on an available port, falling back if busy."""
        if self._running:
            return True

        # Try given port; if busy, find next available
        actual_port = self.port
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.bind((self.host, actual_port))
            test_sock.close()
        except OSError:
            logger.warning("Port %d is busy, searching for available port...", actual_port)
            new_port = self._find_available_port(actual_port + 1)
            if new_port is None:
                logger.error("No available port found in range")
                return False
            actual_port = new_port
            self.port = actual_port

        try:
            LocalServerHandler.token = self.token
            self._server = HTTPServer((self.host, actual_port), LocalServerHandler)
            self._running = True
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
            logger.info("Local server started on %s:%d", self.host, actual_port)
            return True
        except Exception as e:
            logger.error("Failed to start local server: %s", e)
            return False

    def _serve(self) -> None:
        while self._running:
            try:
                self._server.handle_request()
            except Exception as e:
                logger.error("Local server error: %s", e)
                break

    def stop(self) -> None:
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Local server stopped")

    def get_token(self) -> str:
        return self.token
