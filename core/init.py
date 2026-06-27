"""Core package for FelfelDM backend."""

from core.aria2_rpc import Aria2RPC
from core.data_store import DataStore, Queue
from core.aria2_manager import Aria2Manager
from core.websocket_client import WebSocketClient
from core.session_manager import SessionManager
from core.monitor import Aria2Monitor
from core.updater import Updater
from core.error_handler import ErrorHandler
from core.ssl_utils import create_ssl_context, get_fingerprint_from_cert

__all__ = [
    "Aria2RPC",
    "DataStore",
    "Queue",
    "Aria2Manager",
    "WebSocketClient",
    "SessionManager",
    "Aria2Monitor",
    "Updater",
    "ErrorHandler",
    "create_ssl_context",
    "get_fingerprint_from_cert",
]
