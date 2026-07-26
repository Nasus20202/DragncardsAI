from __future__ import annotations

import asyncio


class InflightRegistry:
    """Tracks the asyncio task evaluating each in-flight target.

    Lets a cancel request abort the in-flight judge call promptly by cancelling
    the owning task (which cancels the awaited httpx stream/request). This is
    purely transient process bookkeeping; the authoritative ``cancelled`` status
    is written to Postgres by the cancel handler.
    """

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task[None]] = {}

    def register(self, target_id: int, task: asyncio.Task[None]) -> None:
        self._tasks[target_id] = task

    def unregister(
        self, target_id: int, task: asyncio.Task[None] | None = None
    ) -> None:
        """Drop the registered task for ``target_id``.

        When ``task`` is given, the entry is removed only if it is still that
        exact task: a stale task finishing its ``finally`` must not evict a newer
        task that a force re-claim already registered for the same target_id
        (which would otherwise leave the live task uncancellable).
        """
        if task is not None and self._tasks.get(target_id) is not task:
            return
        self._tasks.pop(target_id, None)

    def cancel(self, target_id: int) -> bool:
        """Cancel the in-flight task for ``target_id`` if any. Returns True when
        a running task was found and cancelled."""
        task = self._tasks.get(target_id)
        if task is None or task.done():
            return False
        task.cancel()
        return True
