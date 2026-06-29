# core/aria2_rpc.py
"""
aria2 RPC client with batch call support via system.multicall,
SSL validation, and connection caching.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

import requests

from core.constants import DEFAULT_TIMEOUT, DEFAULT_BATCH_TIMEOUT

logger = logging.getLogger(__name__)


class Aria2RPC:
    """
    aria2 RPC client with batch call support via system.multicall and SSL validation.
    Uses a persistent requests.Session with keep-alive for connection caching.
    """

    DEFAULT_TIMEOUT: int = DEFAULT_TIMEOUT
    DEFAULT_BATCH_TIMEOUT: int = DEFAULT_BATCH_TIMEOUT

    def __init__(
        self,
        host: str = "http://localhost",
        port: int = 6800,
        secret: str = "",
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.url = f"{host}:{port}/jsonrpc"
        self.secret = secret
        self._id = 0
        self.on_error = None
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        self._session = requests.Session()
        self._session.verify = verify_ssl
        self._session.headers.update({"Connection": "keep-alive"})

        if not verify_ssl:
            logger.warning(
                "SSL verification is disabled. This is insecure and should only be used for testing."
            )

    # ... بقیه متدها به‌جز تغییر در استفاده از DEFAULT_BATCH_TIMEOUT

    def batch_call(
        self,
        calls: List[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> List[Any]:
        """Execute multiple RPC calls in a single request using system.multicall."""
        if not calls:
            return []

        params = self._prepare_multicall_params(calls)

        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._id),
            "method": "system.multicall",
            "params": [params],
        }

        timeout_sec = timeout if timeout is not None else self.DEFAULT_BATCH_TIMEOUT

        try:
            r = self._session.post(self.url, json=payload, timeout=timeout_sec)
            result = r.json()

            if "error" in result:
                err = result["error"]
                msg = f"multicall error: {err.get('message', err)}"
                logger.warning(msg)
                if self.on_error:
                    self.on_error(msg)
                return [None] * len(calls)

            raw_results = result.get("result")
            return self._process_multicall_results(raw_results, len(calls))

        except requests.exceptions.ConnectionError:
            msg = "aria2 disconnected during batch call"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)
        except requests.exceptions.Timeout:
            msg = "aria2 timeout during batch call"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)
        except Exception as e:
            msg = f"aria2 batch error: {e}"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)
