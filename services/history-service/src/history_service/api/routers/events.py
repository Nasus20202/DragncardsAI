from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from history_service.api.deps import (
    get_repository,
    get_snapshot_service,
)
from history_service.api.validation import GameIdPath
from history_service.runtime.snapshots import SnapshotService
from history_service.schemas.api import (
    BackfillResponse,
    EventListResponse,
    EventResponse,
)
from history_service.schemas.envelope import EventEnvelope
from history_service.storage.repository import Repository

router = APIRouter(tags=["events"])


@router.post("/games/{game_id}/events", response_model=BackfillResponse)
async def backfill_event(
    request: Request,
    game_id: GameIdPath,
    envelope: EventEnvelope,
    repo: Repository = Depends(get_repository),
    snapshots: SnapshotService = Depends(get_snapshot_service),
) -> BackfillResponse:
    """HTTP backfill: persist an envelope using the same ordering/idempotency rules.

    The path ``game_id`` is authoritative; it overrides any mismatched body value
    so backfills always land under the addressed game.
    """
    if envelope.game_id != game_id:
        envelope = envelope.model_copy(update={"game_id": game_id})
    result = await repo.commit_event(envelope)
    if result.inserted:
        # Best-effort: a snapshot failure must never turn a committed event into
        # an error response.
        await snapshots.maybe_snapshot_best_effort(game_id, result.event.seq)
    return BackfillResponse(
        game_id=game_id, seq=result.event.seq, inserted=result.inserted
    )


@router.get("/games/{game_id}/events", response_model=EventListResponse)
async def list_events(
    game_id: GameIdPath,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    repo: Repository = Depends(get_repository),
) -> EventListResponse:
    events = await repo.list_events(game_id, after_seq=after_seq, limit=limit)
    next_after = events[-1].seq if len(events) == limit else None
    return EventListResponse(
        game_id=game_id,
        events=[EventResponse.from_stored(event) for event in events],
        next_after_seq=next_after,
    )
