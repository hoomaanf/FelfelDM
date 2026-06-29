# =============================================================================
# core/local_server.py
# =============================================================================
import json
import secrets
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse

logger = logging.getLogger(__name__)

# Token storage
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

        # Create new token
        token = secrets.token_urlsafe(32)
        try:
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump({"token": token}, f, indent=2)
            # Restrict permissions
            TOKEN_FILE.chmod(0o600)
        except Exception as e:
            logger.error("Failed to save token: %s", e)
        return token


class LocalServerHandler(BaseHTTPRequestHandler):
    """HTTP handler for browser extension communication."""

    token: str = ""  # class variable set by server

    def do_GET(self):
        """Handle GET requests from browser extension."""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/token":
            self.send_error(404, "Not found")
            return

        # Verify token from query parameter
        query = urllib.parse.parse_qs(parsed.query)
        provided_token = query.get("token", [None])[0]
        if provided_token != self.token:
            self.send_error(401, "Unauthorized")
            return

        # Respond with RPC info
        response = {
            "host": self.server.server_address[0],
            "port": self.server.server_address[1],
            "secret": self.token,  # extension uses secret for aria2
            "protocol": "http"
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode("utf-8"))

    def log_message(self, format, *args):
        """Suppress verbose logging."""
        pass


class LocalServer:
    """HTTP server for browser extension integration."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.token = TokenManager.get_or_create_token()

    def start(self) -> bool:
        """Start the HTTP server in a background thread."""
        if self._running:
            return True
        try:
            # Set token as class variable for handler
            LocalServerHandler.token = self.token
            self._server = HTTPServer((self.host, self.port), LocalServerHandler)
            self._running = True
            self._thread = threading.Thread(target=self._serve, daemon=True)
            self._thread.start()
            logger.info("Local server started on %s:%d", self.host, self.port)
            return True
        except Exception as e:
            logger.error("Failed to start local server: %s", e)
            return False

    def _serve(self) -> None:
        """Serve requests until stopped."""
        while self._running:
            try:
                self._server.handle_request()
            except Exception as e:
                logger.error("Local server error: %s", e)
                break

    def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Local server stopped")

    def get_token(self) -> str:
        """Return the current token."""
        return self.token
