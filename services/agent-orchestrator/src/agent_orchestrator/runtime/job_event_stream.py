from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from agent_orchestrator.runtime.live_events import LiveEventBus, LiveJobEvent
from agent_orchestrator.schemas.jobs import JobEventResponse
from agent_orchestrator.storage.repository import Repository

TERMINAL_EVENT_TYPES = {"completion", "failure", "cancellation"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def serialize_live_event(event: LiveJobEvent) -> JobEventResponse:
    """Render a live-bus event as the stream's client sees it.

    This stream has two sources for the same event: it polls ``list_events`` for
    durable rows and it forwards the live bus, and almost every publish is
    preceded by an ``append_event``. So most live events are a second copy of a
    row this stream also yields from Postgres — sent early, because that is the
    whole point of the bus.

    Both copies must therefore reach the client under the *same* id, since the
    id is what the client de-duplicates on. When the publisher recorded a
    durable row it says so via ``durable_event_id``, and that id wins over the
    bus's own (a Valkey stream entry id, or an in-memory counter) which
    identifies the delivery rather than the event. Losing this is what made one
    question render as two cards (DRA-34).
    """
    return JobEventResponse(
        id=str(event.durable_event_id or event.id),
        event_type=event.event_type,
        payload=event.payload_json,
        created_at=event.created_at,
    )


def format_sse_event(
    *,
    event_type: str,
    payload: JobEventResponse,
    event_id: str | None = None,
) -> str:
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(payload.model_dump(mode='json'))}")
    return "\n".join(lines) + "\n\n"


class JobEventStreamService:
    def __init__(
        self,
        *,
        repository: Repository,
        live_event_bus: LiveEventBus,
        poll_interval_seconds: float,
    ):
        self._repository = repository
        self._live_event_bus = live_event_bus
        self._poll_interval_seconds = poll_interval_seconds

    async def stream(
        self,
        job_id: str,
        *,
        after: int = 0,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[str]:
        cursor = after
        terminal_received = False
        live_subscriber = await self._live_event_bus.subscribe(job_id)
        try:
            while True:
                if is_disconnected is not None and await is_disconnected():
                    return

                events = await asyncio.shield(
                    self._repository.list_events(job_id, after_id=cursor)
                )
                for event in events:
                    cursor = event.id
                    payload = JobEventResponse(
                        id=str(event.id),
                        event_type=event.event_type,
                        payload=event.payload_json,
                        created_at=event.created_at,
                    )
                    yield format_sse_event(
                        event_type=event.event_type,
                        payload=payload,
                        event_id=str(event.id),
                    )
                    if event.event_type in TERMINAL_EVENT_TYPES:
                        terminal_received = True

                if terminal_received and not events:
                    return

                if is_disconnected is not None and await is_disconnected():
                    return

                live_event = await live_subscriber.get(self._poll_interval_seconds)
                if live_event is None:
                    job = await asyncio.shield(self._repository.get_job(job_id))
                    if job is None:
                        return
                    if job.status in TERMINAL_JOB_STATUSES:
                        trailing_events = await asyncio.shield(
                            self._repository.list_events(job_id, after_id=cursor)
                        )
                        for event in trailing_events:
                            cursor = event.id
                            payload = JobEventResponse(
                                id=str(event.id),
                                event_type=event.event_type,
                                payload=event.payload_json,
                                created_at=event.created_at,
                            )
                            yield format_sse_event(
                                event_type=event.event_type,
                                payload=payload,
                                event_id=str(event.id),
                            )
                        return
                    continue

                live_payload = serialize_live_event(live_event)
                yield format_sse_event(
                    event_type=live_event.event_type,
                    payload=live_payload,
                    event_id=live_payload.id,
                )
                if live_event.event_type in TERMINAL_EVENT_TYPES:
                    terminal_received = True
        except asyncio.CancelledError, GeneratorExit:
            return
        finally:
            # Use shield so the subscriber cleanup is not interrupted by
            # GeneratorExit or CancelledError thrown by Starlette when a client
            # disconnects mid-stream.
            try:
                await asyncio.shield(live_subscriber.aclose())
            except asyncio.CancelledError, GeneratorExit:
                pass
