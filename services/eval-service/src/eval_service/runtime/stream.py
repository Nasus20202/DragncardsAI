from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any, Awaitable

from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.status import request_status, to_target_result
from eval_service.storage.models import EvaluatedTargetRow
from eval_service.storage.repository import Repository

logger = logging.getLogger(__name__)

KEEPALIVE_SECONDS = 15.0
# Terminal target statuses (the request is done once all targets are terminal).
_TERMINAL = {"completed", "skipped", "failed", "cancelled"}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class EvaluationStreamService:
    """Builds the SSE byte stream for one evaluation request.

    Durable status/verdicts are read from Postgres; the live bus only signals
    "something changed" so the stream re-reads the authoritative snapshot and
    diffs it. ``token`` events are forwarded straight from the bus (they carry
    no durable state). A ~15s keepalive comment keeps proxies from idling out.
    """

    def __init__(self, *, repository: Repository, live_bus: LiveEventBus):
        self._repository = repository
        self._live_bus = live_bus

    async def stream(
        self,
        request_id: str,
        *,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[str]:
        queue = self._live_bus.subscribe(request_id)
        try:
            targets = await self._repository.list_targets_for_request(request_id)
            # Initial full snapshot on connect.
            yield _sse("status", self._status_payload(request_id, targets))
            emitted_verdicts: set[int] = set()

            # Emit verdicts already present at connect time.
            for chunk in self._verdict_events(targets, emitted_verdicts):
                yield chunk

            if self._is_done(targets):
                yield _sse(
                    "done",
                    {"request_id": request_id, "status": request_status(targets)},
                )
                return

            while True:
                if is_disconnected is not None and await is_disconnected():
                    return
                try:
                    event, data = await asyncio.wait_for(
                        queue.get(), timeout=KEEPALIVE_SECONDS
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event == "token":
                    yield _sse("token", data)
                    continue

                # Any non-token signal -> re-read the durable snapshot and emit
                # a fresh status plus any newly completed verdicts.
                targets = await self._repository.list_targets_for_request(request_id)
                yield _sse("status", self._status_payload(request_id, targets))
                for chunk in self._verdict_events(targets, emitted_verdicts):
                    yield chunk
                if self._is_done(targets):
                    yield _sse(
                        "done",
                        {"request_id": request_id, "status": request_status(targets)},
                    )
                    return
        finally:
            self._live_bus.unsubscribe(request_id, queue)

    def _status_payload(
        self, request_id: str, targets: list[EvaluatedTargetRow]
    ) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "status": request_status(targets),
            "targets": [to_target_result(t).model_dump(mode="json") for t in targets],
        }

    def _verdict_events(
        self, targets: list[EvaluatedTargetRow], emitted: set[int]
    ) -> list[str]:
        events: list[str] = []
        for t in targets:
            if (
                t.status == "completed"
                and t.verdict_json is not None
                and t.id not in emitted
            ):
                emitted.add(t.id)
                events.append(
                    _sse(
                        "verdict",
                        {
                            "target_seq": t.target_seq,
                            "scope": t.scope,
                            "verdict": t.verdict_json,
                        },
                    )
                )
        return events

    @staticmethod
    def _is_done(targets: list[EvaluatedTargetRow]) -> bool:
        return bool(targets) and all(t.status in _TERMINAL for t in targets)
