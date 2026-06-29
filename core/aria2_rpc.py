# =============================================================================
# core/aria2_rpc.py
# =============================================================================
import json
import logging
from typing import Optional, List, Any, Dict

import requests

from core.aria2_rpc_base import BaseAria2RPC

logger = logging.getLogger(__name__)


class Aria2RPC(BaseAria2RPC):
    """Synchronous client for aria2 RPC using requests."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6800,
                 secret: str = "", verify_ssl: bool = True) -> None:
        super().__init__(host, port, secret, verify_ssl)

    def _send_request(self, payload: Dict[str, Any]) -> Optional[Any]:
        """Send request synchronously using requests.post."""
        url = self._build_url()
        try:
            resp = requests.post(url, json=payload, verify=self.verify_ssl, timeout=30)
            if resp.status_code != 200:
                logger.error("RPC error: %d %s", resp.status_code, resp.text)
                return None
            return resp.json()
        except Exception as e:
            logger.error("RPC exception: %s", e)
            return None
