# core/service_container.py
"""
Service Container for dependency injection and service management.
Handles creation, caching, and lifecycle of all core services.
"""

import logging
from typing import Any, Callable, Dict, Optional, Type, TypeVar, cast

from core.constants import ARIA2_DEFAULT_HOST, ARIA2_DEFAULT_PORT
from core.data_store import DataStore
from core.aria2_manager import Aria2Manager
from core.aria2_rpc import Aria2RPC
from core.aria2_rpc_async import AsyncAria2RPC
from core.history import HistoryManager
from core.worker import BackendWorker
from core.async_worker import AsyncWorker

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ServiceContainer:
    """
    Simple Service Container for dependency injection.

    Supports:
        - Singleton services (cached)
        - Factory services (new instance each time)
        - Lazy initialization
        - Dependency resolution
    """

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._factories: Dict[str, Callable[[], Any]] = {}
        self._singletons: Dict[str, bool] = {}

    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        singleton: bool = True,
    ) -> None:
        """
        Register a service with a factory function.

        Args:
            name: Unique service identifier
            factory: Callable that returns the service instance
            singleton: If True, the same instance will be returned on each resolve
        """
        self._factories[name] = factory
        self._singletons[name] = singleton
        # Clear cached instance if exists
        if name in self._services:
            del self._services[name]
        logger.debug("Registered service: %s (singleton=%s)", name, singleton)

    def resolve(self, name: str) -> Any:
        """
        Resolve a service by name.

        Args:
            name: Service identifier

        Returns:
            The service instance

        Raises:
            KeyError: If the service is not registered
        """
        if name not in self._factories:
            raise KeyError(f"Service '{name}' not registered")

        # Return cached singleton if exists
        if self._singletons.get(name, True) and name in self._services:
            return self._services[name]

        # Build instance
        instance = self._factories[name]()
        if self._singletons.get(name, True):
            self._services[name] = instance
        return instance

    def has(self, name: str) -> bool:
        """Check if a service is registered."""
        return name in self._factories

    def clear(self) -> None:
        """Clear all cached instances."""
        self._services.clear()

    def __getitem__(self, name: str) -> Any:
        """Convenience method for resolve."""
        return self.resolve(name)

    def __contains__(self, name: str) -> bool:
        """Check if a service is registered."""
        return self.has(name)


def create_container() -> ServiceContainer:
    """
    Create and configure the service container with all core services.

    Returns:
        Configured ServiceContainer instance
    """
    container = ServiceContainer()

    # =========================================================================
    # 1. DataStore - loads settings from disk
    # =========================================================================
    def _build_data_store() -> DataStore:
        return DataStore()

    container.register('data_store', _build_data_store, singleton=True)

    # =========================================================================
    # 2. HistoryManager - depends on nothing (except file system)
    # =========================================================================
    def _build_history_manager() -> HistoryManager:
        return HistoryManager()

    container.register('history_manager', _build_history_manager, singleton=True)

    # =========================================================================
    # 3. Aria2RPC - depends on DataStore settings
    # =========================================================================
    def _build_aria2_rpc() -> Aria2RPC:
        store = container.resolve('data_store')
        settings = store.settings
        return Aria2RPC(
            host=settings.aria2_host,
            port=settings.aria2_port,
            secret=store.get_secret(),
            verify_ssl=True,
            timeout=Aria2RPC.DEFAULT_TIMEOUT,
        )

    container.register('aria2_rpc', _build_aria2_rpc, singleton=True)

    # =========================================================================
    # 4. AsyncAria2RPC - depends on DataStore settings
    # =========================================================================
    def _build_async_aria2_rpc() -> AsyncAria2RPC:
        store = container.resolve('data_store')
        settings = store.settings
        return AsyncAria2RPC(
            host=settings.aria2_host,
            port=settings.aria2_port,
            secret=store.get_secret(),
            verify_ssl=True,
            timeout=AsyncAria2RPC.DEFAULT_TIMEOUT,
        )

    container.register('async_aria2_rpc', _build_async_aria2_rpc, singleton=True)

    # =========================================================================
    # 5. Aria2Manager - standalone (starts aria2 subprocess)
    # =========================================================================
    def _build_aria2_manager() -> Aria2Manager:
        return Aria2Manager()

    container.register('aria2_manager', _build_aria2_manager, singleton=True)

    # =========================================================================
    # 6. BackendWorker (sync) - depends on Aria2RPC and DataStore
    # =========================================================================
    def _build_backend_worker() -> BackendWorker:
        aria2_rpc = container.resolve('aria2_rpc')
        data_store = container.resolve('data_store')
        return BackendWorker(
            aria2=aria2_rpc,
            store=data_store,
            poll_interval=data_store.settings.get('poll_interval', 1000),
            use_async=False,
        )

    container.register('backend_worker', _build_backend_worker, singleton=True)

    # =========================================================================
    # 7. AsyncWorker - depends on AsyncAria2RPC and DataStore
    # =========================================================================
    def _build_async_worker() -> AsyncWorker:
        async_aria2_rpc = container.resolve('async_aria2_rpc')
        data_store = container.resolve('data_store')
        return AsyncWorker(
            aria2=async_aria2_rpc,
            store=data_store,
            poll_interval=data_store.settings.get('poll_interval', 1000),
        )

    container.register('async_worker', _build_async_worker, singleton=True)

    # =========================================================================
    # 8. Worker (auto-select) - returns BackendWorker or AsyncWorker based on settings
    # =========================================================================
    def _build_worker() -> Any:
        store = container.resolve('data_store')
        use_async = store.settings.get('async_mode', False)
        if use_async:
            logger.info("Using AsyncWorker (async mode enabled)")
            return container.resolve('async_worker')
        else:
            logger.info("Using BackendWorker (sync mode)")
            return container.resolve('backend_worker')

    container.register('worker', _build_worker, singleton=True)

    # =========================================================================
    # 9. LocalServer - depends on DownloadController (built in main_window)
    #    Not registered here because it depends on UI components.
    # =========================================================================

    return container


# Global container instance (singleton)
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """
    Get the global service container instance.

    Returns:
        Configured ServiceContainer instance
    """
    global _container
    if _container is None:
        _container = create_container()
    return _container


def reset_container() -> None:
    """Reset the global container (mainly for testing)."""
    global _container
    if _container is not None:
        _container.clear()
    _container = None
