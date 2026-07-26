from __future__ import annotations

from typing import Any
from urllib.parse import quote

from dragncards_common.http_client import BaseAsyncClient

from eval_service.schemas.history import StoredEvent


class HistoryClient(BaseAsyncClient):
    """HTTP client for the history-service read + ingest endpoints.

    Reads the per-game event timeline (paginated) and writes verdict events
    back through the ingest endpoint. The same long-lived client is reused so
    repeated calls share one connection pool.
    """

    def __init__(
        self,
        base_url: str,
        *,
        page_size: int = 1000,
        timeout_seconds: float = 30.0,
    ):
        super().__init__(base_url, timeout_seconds=timeout_seconds)
        self._page_size = page_size

    async def list_all_events(self, game_id: str) -> list[StoredEvent]:
        """Return every event for a game, paginating until exhausted."""
        events: list[StoredEvent] = []
        after_seq = 0
        while True:
            page = await self._fetch_page(game_id, after_seq)
            raw_events = page.get("events") or []
            for raw in raw_events:
                events.append(StoredEvent.model_validate(raw))
            next_after = page.get("next_after_seq")
            if next_after is None or not raw_events:
                break
            after_seq = int(next_after)
        return events

    async def _fetch_page(self, game_id: str, after_seq: int) -> dict[str, Any]:
        # URL-encode the path segment so a game_id never breaks out of the path
        # (defense-in-depth even though the route layer already validates it).
        response = await self._http().get(
            f"{self._base_url}/games/{quote(game_id, safe='')}/events",
            params={"after_seq": after_seq, "limit": self._page_size},
        )
        response.raise_for_status()
        return response.json()

    async def write_event(
        self, game_id: str, envelope: dict[str, Any]
    ) -> dict[str, Any]:
        """Submit a verdict envelope to the history ingest endpoint.

        The history-service dedupes on ``(game_id, idempotency_key)``, so a
        duplicate write-back is stored exactly once.
        """
        response = await self._http().post(
            f"{self._base_url}/games/{quote(game_id, safe='')}/events",
            json=envelope,
        )
        response.raise_for_status()
        return response.json()
