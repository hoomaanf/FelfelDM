# core/__init__.py
"""
Core module exports for FelfelDM.
"""

from core.aria2_manager import Aria2Manager, CertificateManager
from core.aria2_rpc import Aria2RPC
from core.aria2_rpc_async import AsyncAria2RPC
from core.async_worker import AsyncWorker
from core.data_store import DataStore, Settings
from core.error_handler import ErrorHandler
from core.history import HistoryManager
from core.local_server import LocalServer
from core.monitor import Aria2Monitor
from core.queue_model import Queue
from core.service_container import ServiceContainer, create_container, get_container, reset_container
from core.session_manager import SessionManager
from core.ssl_utils import create_ssl_context, get_fingerprint_from_cert
from core.updater import Updater
from core.websocket_client import WebSocketClient
from core.worker import BackendWorker

__all__ = [
    "Aria2Manager",
    "Aria2Monitor",
    "Aria2RPC",
    "AsyncAria2RPC",
    "AsyncWorker",
    "BackendWorker",
    "CertificateManager",
    "DataStore",
    "ErrorHandler",
    "HistoryManager",
    "LocalServer",
    "Queue",
    "ServiceContainer",
    "SessionManager",
    "Settings",
    "Updater",
    "WebSocketClient",
    "create_container",
    "create_ssl_context",
    "get_container",
    "get_fingerprint_from_cert",
    "reset_container",
]
