from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from history_service.api.deps import get_repository, get_settings
from history_service.api.validation import GameIdPath, GameIdQuery
from history_service.config import Settings
from history_service.runtime.transfer import (
    BundleError,
    BundleReader,
    BundleTooLargeError,
    bundle_filename,
    iter_export_lines,
)
from history_service.schemas.transfer import BUNDLE_MEDIA_TYPE, ImportResponse
from history_service.storage.repository import (
    DuplicateImportRecordError,
    GameHistoryExistsError,
    Repository,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transfer"])


@router.get(
    "/games/{game_id}/export",
    response_class=StreamingResponse,
    summary="Export a game's history as a human-readable NDJSON bundle",
)
async def export_game(
    game_id: GameIdPath,
    repo: Repository = Depends(get_repository),
) -> StreamingResponse:
    """Stream the game's complete recorded history as NDJSON.

    One JSON object per line, keys sorted: a ``header``, one ``event`` per stored
    event in ascending ``seq``, one ``snapshot`` per stored snapshot in ascending
    ``snapshot_at_seq``, then a ``footer`` repeating the counts. Nothing outside
    the history store is read, so no service configuration or credential can
    reach the file.

    An unknown game exports a header/footer pair with zero counts rather than an
    error, matching the read endpoints' convention; importing such a bundle is
    what fails loudly.
    """
    return StreamingResponse(
        iter_export_lines(repo, game_id),
        media_type=BUNDLE_MEDIA_TYPE,
        headers={
            "content-disposition": (
                f'attachment; filename="{bundle_filename(game_id)}"'
            )
        },
    )


@router.post("/import", response_model=ImportResponse)
async def import_game(
    request: Request,
    game_id: GameIdQuery = None,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> ImportResponse:
    """Import an NDJSON bundle as a new game's history.

    Non-destructive by design: the target is ``game_id`` when given, otherwise
    the bundle header's own ``game_id``, and a target that already has recorded
    history is refused with 409 rather than merged into or overwritten. Putting
    an imported game onto a live board is a separate, existing operation
    (``POST /games/{game_id}/restore``).

    The bundle is validated record by record as it streams and written inside a
    single transaction, so a malformed, truncated, or oversized file imports
    nothing and the response says which line was at fault.
    """
    # Refuse an oversized upload on its declared size before reading a byte; the
    # streaming reader enforces the same ceiling against what actually arrives,
    # so a missing or lying Content-Length changes nothing.
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit():
        if int(declared) > settings.history_import_max_bytes:
            raise HTTPException(status_code=413, detail="Request body too large")

    reader = BundleReader(request.stream(), max_bytes=settings.history_import_max_bytes)

    try:
        header = await reader.read_header()
        # The target is the caller's choice when given, else the bundle's own id.
        target_game_id = game_id or header.game_id
        result = await repo.import_game_history(target_game_id, reader.records())
    except BundleTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except BundleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GameHistoryExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except DuplicateImportRecordError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "Imported %s events and %s snapshots into game=%s (from %s)",
        result.imported_events,
        result.imported_snapshots,
        result.game_id,
        header.game_id,
    )
    return ImportResponse(
        game_id=result.game_id,
        source_game_id=header.game_id,
        imported_events=result.imported_events,
        imported_snapshots=result.imported_snapshots,
        first_seq=result.first_seq,
        last_seq=result.last_seq,
    )
