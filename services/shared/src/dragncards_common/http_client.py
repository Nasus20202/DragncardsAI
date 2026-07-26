"""Thin base for services' lazy ``httpx.AsyncClient`` wrappers.

Several internal HTTP clients share the same lifecycle: a base URL, a timeout, a
lazily-created :class:`httpx.AsyncClient` reused across calls (one connection
pool), an idempotent ``aclose``, and a ``GET /health`` probe. Subclasses add
their own endpoint methods on top of :meth:`_http`.
"""

from __future__ import annotations

import httpx


class BaseAsyncClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        """Return a long-lived client so repeated calls reuse one connection pool."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        try:
            response = await self._http().get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200
