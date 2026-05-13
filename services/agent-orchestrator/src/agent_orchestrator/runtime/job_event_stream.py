from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable

from agent_orchestrator.runtime.live_events import LiveEventBus, LiveJobEvent
from agent_orchestrator.schemas.jobs import JobEventResponse
from agent_orchestrator.storage.repository import Repository

TERMINAL_EVENT_TYPES = {"completion", "failure", "cancellation"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


def serialize_live_event(event: LiveJobEvent) -> JobEventResponse:
    return JobEventResponse(
        id=str(event.id),
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

                yield format_sse_event(
                    event_type=live_event.event_type,
                    payload=serialize_live_event(live_event),
                )
                if live_event.event_type in TERMINAL_EVENT_TYPES:
                    terminal_received = True
        except asyncio.CancelledError:
            return
        finally:
            await live_subscriber.aclose()
