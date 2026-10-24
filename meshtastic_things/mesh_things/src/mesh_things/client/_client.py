"""The sync and async clients, with one namespace per API tag and one method per operation."""
import asyncio
import time
from typing import TYPE_CHECKING, Any, Callable

import httpx

from . import _core
from .errors import Throttled
from .schema import Operation, operations

if TYPE_CHECKING:
    from ._namespaces import AsyncNamespaces, SyncNamespaces
else:
    AsyncNamespaces = SyncNamespaces = object


class Namespace:
    """The operations of one API tag, for example `meshes`."""

    def __init__(self, name: str):
        self._name = name

    def __repr__(self) -> str:
        methods = sorted(m for m in vars(self) if not m.startswith("_"))
        return f"<{self._name}: {', '.join(methods)}>"


class _Client:
    def __init__(
        self,
        base_url: str | None,
        api_key: str | None,
        readings_url: str | None,
        retries: int,
    ):
        self.base_url = _core.resolve_base_url(base_url)
        self.readings_url = readings_url.rstrip("/") if readings_url else None
        self.retries = retries
        key = _core.resolve_api_key(api_key)
        self._headers = {"Authorization": f"Bearer {key}"} if key else {}
        self._versions_warned: set[str] = set()
        namespaces: dict[str, Namespace] = {}
        for op in operations().values():
            if op.namespace not in namespaces:
                namespaces[op.namespace] = Namespace(op.namespace)
                setattr(self, op.namespace, namespaces[op.namespace])
            setattr(namespaces[op.namespace], op.name, self._bind(op))

    def _bind(self, op: Operation) -> Callable[..., Any]:
        raise NotImplementedError

    def _prepare(self, operation_id: str, args: tuple, kwargs: dict):
        op = operations()[operation_id]
        _core.warn_if_deprecated(op)
        return op, _core.prepare(op, self.base_url, self.readings_url, args, kwargs)

    def _finish(self, op: Operation, response: httpx.Response) -> Any:
        _core.check_version(response, self._versions_warned)
        return _core.result(op, response)

    @staticmethod
    def _decorate(fn, op: Operation):
        fn.__name__ = op.name
        fn.__qualname__ = f"{op.namespace}.{op.name}"
        fn.__doc__ = op.description
        fn.__signature__ = _core.signature(op)
        return fn

    def _retry_delay(self, error: Throttled, attempt: int) -> float | None:
        if attempt >= self.retries or error.retry_after is None:
            return None
        return error.retry_after


class MeshThings(_Client, SyncNamespaces):
    """Client for the meshtastic-things API.

    Args:
        base_url: The API's root, for example `https://api.example.org`. Defaults to
            `MESH_THINGS_URL`.
        api_key: An owner's API key. Defaults to `MESH_THINGS_API_KEY`; without one only
            public data can be read.
        readings_url: A separate root for `/readings` paths, for a local stack that serves
            them on their own port.
        timeout: Seconds before a request is abandoned.
        retries: How many times a rate-limited request is retried after the delay the API
            asks for.
        http: An `httpx.Client` to send requests with, instead of a new one.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        readings_url: str | None = None,
        timeout: float = 30.0,
        retries: int = 0,
        http: httpx.Client | None = None,
    ):
        self._http = http or httpx.Client(timeout=timeout)
        super().__init__(base_url, api_key, readings_url, retries)

    def call(self, operation_id: str, *args: Any, **kwargs: Any) -> Any:
        """Run any operation by its operationId."""
        op, request = self._prepare(operation_id, args, kwargs)
        attempt = 0
        while True:
            response = self._http.request(
                request.method, request.url, params=request.params, json=request.json, headers=self._headers,
            )
            try:
                return self._finish(op, response)
            except Throttled as error:
                delay = self._retry_delay(error, attempt)
                if delay is None:
                    raise
                attempt += 1
                time.sleep(delay)

    def _bind(self, op: Operation) -> Callable[..., Any]:
        def method(*args, **kwargs):
            return self.call(op.operation_id, *args, **kwargs)
        return self._decorate(method, op)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "MeshThings":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncMeshThings(_Client, AsyncNamespaces):
    """Async client for the meshtastic-things API. Takes the same arguments as `MeshThings`."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        *,
        readings_url: str | None = None,
        timeout: float = 30.0,
        retries: int = 0,
        http: httpx.AsyncClient | None = None,
    ):
        self._http = http or httpx.AsyncClient(timeout=timeout)
        super().__init__(base_url, api_key, readings_url, retries)

    async def call(self, operation_id: str, *args: Any, **kwargs: Any) -> Any:
        """Run any operation by its operationId."""
        op, request = self._prepare(operation_id, args, kwargs)
        attempt = 0
        while True:
            response = await self._http.request(
                request.method, request.url, params=request.params, json=request.json, headers=self._headers,
            )
            try:
                return self._finish(op, response)
            except Throttled as error:
                delay = self._retry_delay(error, attempt)
                if delay is None:
                    raise
                attempt += 1
                await asyncio.sleep(delay)

    def _bind(self, op: Operation) -> Callable[..., Any]:
        async def method(*args, **kwargs):
            return await self.call(op.operation_id, *args, **kwargs)
        return self._decorate(method, op)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "AsyncMeshThings":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
