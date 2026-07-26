from __future__ import annotations

import asyncio
from typing import Any


class LiveEventBus:
    """In-process pub/sub for pushing live evaluation progress to SSE clients.

    This is a TRANSIENT push channel only: all durable state (target/request
    status, verdicts) lives in Postgres. The bus exists so a connected SSE
    stream is woken immediately on a transition or token instead of polling.
    A subscriber that misses an event (e.g. connected late) still gets a correct
    view because the stream reads the authoritative snapshot from Postgres.

    Events are plain ``(event_name, data)`` tuples scoped by ``request_id``.
    """

    def __init__(self, *, max_queue: int = 1000):
        self._subscribers: dict[str, set[asyncio.Queue[Any]]] = {}
        self._max_queue = max_queue

    def subscribe(self, request_id: str) -> asyncio.Queue[Any]:
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._max_queue)
        self._subscribers.setdefault(request_id, set()).add(queue)
        return queue

    def has_subscribers(self, request_id: str) -> bool:
        """True when at least one SSE client is currently watching ``request_id``."""
        return bool(self._subscribers.get(request_id))

    def unsubscribe(self, request_id: str, queue: asyncio.Queue[Any]) -> None:
        subs = self._subscribers.get(request_id)
        if subs is None:
            return
        subs.discard(queue)
        if not subs:
            self._subscribers.pop(request_id, None)

    def publish(self, request_id: str, event: str, data: dict[str, Any]) -> None:
        """Best-effort push to all live subscribers of ``request_id``.

        Never blocks the publisher: if a slow consumer's queue is full the event
        is dropped for that consumer (the consumer re-reads the durable snapshot
        from Postgres on the next event, so it self-heals).
        """
        for queue in self._subscribers.get(request_id, set()):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:  # noqa: PERF203 - rare, isolate per consumer
                pass
