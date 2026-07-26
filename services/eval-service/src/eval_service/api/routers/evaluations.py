from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from eval_service.api.deps import (
    get_inflight,
    get_live_bus,
    get_repository,
    get_request_service,
    get_stream_service,
    get_worker,
)
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.requests import (
    GameNotFoundError,
    RequestError,
    RequestService,
)
from eval_service.runtime.status import request_status, to_target_result
from eval_service.runtime.stream import EvaluationStreamService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import (
    CancelResponse,
    ClearEvaluationsResponse,
    CreateEvaluationResponse,
    EvaluationListItem,
    EvaluationListResponse,
    EvaluationRequestBody,
    RequestStatusResponse,
)
from eval_service.storage.models import NON_TERMINAL_STATUSES
from eval_service.storage.repository import Repository

router = APIRouter(tags=["evaluations"])

# Hard ceiling on the cross-game listing so a single request can never page an
# unbounded number of rows out of Postgres. A larger ``limit`` is clamped down.
_LIST_LIMIT_CAP = 200

# A game_id is an opaque slug/uuid; reject anything outside a strict charset at
# the route boundary so a malformed value never reaches a downstream URL or
# query. An invalid id cannot identify any game, so it is rejected as 404.
_GAME_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def validate_game_id(game_id: str) -> str:
    if not _GAME_ID_RE.match(game_id):
        raise HTTPException(status_code=404, detail="game not found")
    return game_id


@router.get("/evaluations", response_model=EvaluationListResponse)
async def list_evaluations(
    active: bool = False,
    limit: int = Query(default=50, ge=1),
    repo: Repository = Depends(get_repository),
) -> EvaluationListResponse:
    """Cross-game listing of recent evaluation requests, newest-first.

    Not nested under ``/games/{game_id}``: it spans all games to back a
    persistent queue. ``active=true`` returns only requests with a non-terminal
    target. ``limit`` is clamped to ``_LIST_LIMIT_CAP`` so the response size is
    bounded regardless of the requested value.
    """
    bounded_limit = min(limit, _LIST_LIMIT_CAP)
    rows = await repo.list_requests(limit=bounded_limit, active_only=active)
    items = [
        EvaluationListItem(
            request_id=request_row.request_id,
            game_id=request_row.game_id,
            status=request_status(targets),  # type: ignore[arg-type]
            created_at=request_row.created_at,
            targets=[to_target_result(t) for t in targets],
        )
        for request_row, targets in rows
    ]
    return EvaluationListResponse(requests=items)


@router.post("/evaluations/clear", response_model=ClearEvaluationsResponse)
async def clear_evaluations(
    repo: Repository = Depends(get_repository),
) -> ClearEvaluationsResponse:
    """Clear all fully-terminal evaluation requests from the queue.

    Removes only requests with NO non-terminal target; requests still pending or
    running are left intact (they can only be cancelled, not cleared). Declared
    as a POST (not an unbounded ``DELETE /evaluations`` collection) so the
    bulk-delete is an explicit action. Removes the eval-service's own tracking
    rows only; verdicts already recorded in the history-service are untouched.
    """
    deleted = await repo.delete_terminal_requests()
    return ClearEvaluationsResponse(deleted_count=deleted)


@router.delete("/evaluations/{request_id}", status_code=204)
async def delete_evaluation(
    request_id: str,
    repo: Repository = Depends(get_repository),
) -> None:
    """Delete a single fully-terminal evaluation request from the queue.

    404 if the request does not exist; 409 if it still has a non-terminal
    target (a running request can only be cancelled, never cleared). On success
    the request and its target rows are removed; recorded history verdicts are
    untouched.
    """
    request_row = await repo.get_request(request_id)
    if request_row is None:
        raise HTTPException(status_code=404, detail="evaluation request not found")
    targets = await repo.list_targets_for_request(request_id)
    if any(target.status in NON_TERMINAL_STATUSES for target in targets):
        raise HTTPException(
            status_code=409,
            detail="cannot clear a request with a non-terminal target; cancel it first",
        )
    await repo.delete_request(request_id)
    return None


@router.post(
    "/games/{game_id}/evaluations",
    response_model=CreateEvaluationResponse,
    status_code=201,
)
async def create_evaluation(
    game_id: str = Depends(validate_game_id),
    body: EvaluationRequestBody = ...,
    service: RequestService = Depends(get_request_service),
    worker: EvaluationWorker | None = Depends(get_worker),
) -> CreateEvaluationResponse:
    try:
        response = await service.create(game_id, body)
    except GameNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RequestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if worker is not None and response.created_count:
        worker.notify()
    return response


@router.get(
    "/games/{game_id}/evaluations/{request_id}",
    response_model=RequestStatusResponse,
)
async def get_evaluation(
    request_id: str,
    game_id: str = Depends(validate_game_id),
    repo: Repository = Depends(get_repository),
) -> RequestStatusResponse:
    request_row = await repo.get_request(request_id)
    if request_row is None or request_row.game_id != game_id:
        raise HTTPException(status_code=404, detail="evaluation request not found")
    targets = await repo.list_targets_for_request(request_id)
    target_results = [to_target_result(t) for t in targets]
    return RequestStatusResponse(
        request_id=request_id,
        game_id=game_id,
        status=request_status(targets),  # type: ignore[arg-type]
        targets=target_results,
    )


@router.get("/games/{game_id}/evaluations/{request_id}/stream")
async def stream_evaluation(
    request: Request,
    request_id: str,
    game_id: str = Depends(validate_game_id),
    repo: Repository = Depends(get_repository),
    stream_service: EvaluationStreamService = Depends(get_stream_service),
) -> StreamingResponse:
    request_row = await repo.get_request(request_id)
    if request_row is None or request_row.game_id != game_id:
        raise HTTPException(status_code=404, detail="evaluation request not found")
    return StreamingResponse(
        stream_service.stream(request_id, is_disconnected=request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/games/{game_id}/evaluations/{request_id}/cancel",
    response_model=CancelResponse,
)
async def cancel_evaluation(
    request_id: str,
    game_id: str = Depends(validate_game_id),
    repo: Repository = Depends(get_repository),
    inflight: InflightRegistry = Depends(get_inflight),
    live_bus: LiveEventBus = Depends(get_live_bus),
) -> CancelResponse:
    request_row = await repo.get_request(request_id)
    if request_row is None or request_row.game_id != game_id:
        raise HTTPException(status_code=404, detail="evaluation request not found")

    # Mark non-terminal targets cancelled durably, THEN abort any in-flight
    # judge call for them so a stale finalize can never clobber the cancellation.
    cancelled_ids = await repo.cancel_request_targets(request_id)
    for target_id in cancelled_ids:
        inflight.cancel(target_id)
    # Wake any live SSE subscriber to re-read the cancelled snapshot.
    live_bus.publish(request_id, "status", {"request_id": request_id})
    return CancelResponse(request_id=request_id, cancelled=len(cancelled_ids))
