from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from history_service.schemas.envelope import PLATFORM_DRAGNCARDS, Platform
from history_service.schemas.transfer import (
    BUNDLE_MEDIA_TYPE,
    BundleMode,
    ImportResponse,
)
from history_service.storage.repository import (
    DuplicateImportRecordError,
    GameHistoryExistsError,
    Repository,
)

# An unknown mode is a 422 from FastAPI's own validation rather than a silent
# fall back to the default, so a typo does not quietly hand back prompt material
# the caller meant to leave out.
BundleModeQuery = Annotated[
    BundleMode,
    Query(
        description=(
            "'full' (default) is lossless. 'minimal' omits the LLM prompt "
            "material — an agent move's conversation_context — and nothing else."
        ),
    ),
]

AsNewQuery = Annotated[
    bool,
    Query(
        description=(
            "Import under a freshly minted game id instead of the bundle's own. "
            "Cannot be combined with game_id."
        ),
    ),
]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["transfer"])


@router.get(
    "/games/{game_id}/export",
    response_class=StreamingResponse,
    summary="Export a game's history as a human-readable NDJSON bundle",
    operation_id="export_game_bundle",
)
async def export_game(
    game_id: GameIdPath,
    mode: BundleModeQuery = "full",
    platform: Platform = Query(default=PLATFORM_DRAGNCARDS),
    repo: Repository = Depends(get_repository),
) -> StreamingResponse:
    """Stream the game's complete recorded history as NDJSON.

    One JSON object per line, keys sorted: a ``header``, then ``blob``, ``event``
    and ``snapshot`` records — events in ascending ``seq``, snapshots after them
    in ascending ``snapshot_at_seq`` — then a ``footer`` repeating the counts.

    A recorded game is overwhelmingly repetition, so any repeated value is
    carried once as a ``blob`` record and referenced as ``{"$ref": "b7"}`` from
    wherever it occurs. References only ever name an earlier line, so the bundle
    stays readable and writable in one pass, and each ``blob`` records the path
    where its value was first seen. An object in a payload whose only key is
    ``$ref`` or ``$literal`` is escaped as ``{"$literal": …}`` and unwrapped on
    import, so real data containing the markers round-trips unchanged.

    ``mode=full`` (the default) is lossless. ``mode=minimal`` carries the same
    records but omits the LLM prompt material — an agent move's
    ``conversation_context`` — by removing the key, never by emptying it, and the
    header declares both the mode and the field it left out.

    Nothing outside the history store is read, so no service configuration or
    credential can reach the file.

    An unknown game exports a header/footer pair with zero counts rather than an
    error, matching the read endpoints' convention; importing such a bundle is
    what fails loudly.
    """
    return StreamingResponse(
        iter_export_lines(repo, game_id, mode=mode, platform=platform),
        media_type=BUNDLE_MEDIA_TYPE,
        headers={
            "content-disposition": (
                f'attachment; filename="{bundle_filename(game_id, mode)}"'
            )
        },
    )


@router.post(
    "/import",
    response_model=ImportResponse,
    operation_id="import_game_bundle",
)
async def import_game(
    request: Request,
    game_id: GameIdQuery = None,
    as_new: AsNewQuery = False,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> ImportResponse:
    """Import an NDJSON bundle as a new game's history.

    The target is chosen in this order: ``game_id`` when the caller names one,
    otherwise a freshly minted id when ``as_new=true``, otherwise the bundle
    header's own ``game_id``. Naming a target *and* asking for a new one is a
    400: they are two answers to one question, and guessing which was meant is
    how a game lands in the wrong place.

    Non-destructive by design: a target that already has recorded history is
    refused with 409 rather than merged into or overwritten, and the default is
    deliberately not a fresh id — that would turn the conflict into a silent copy
    and remove the only way to re-import a bundle onto its original id after that
    game's history was deleted. Putting an imported game onto a live board is a
    separate, existing operation (``POST /games/{game_id}/restore``).

    Bundle format versions 1 and 2 are both accepted; version 1 declared its own
    version, so nothing a user has on disk is unversioned or has to be sniffed.

    Payloads are written **verbatim**, so an import onto a different id leaves
    the source ``game_id`` inside recorded conversations and arguments. That is
    deliberate — a captured conversation is the evidence the stored evaluations
    judged, and rewriting an id inside it would produce a transcript no model
    emitted — so the response reports ``source_id_references`` instead of
    pretending the references are not there.

    The bundle is validated record by record as it streams and written inside a
    single transaction, so a malformed, truncated, or oversized file imports
    nothing and the response says which line was at fault.
    """
    if game_id is not None and as_new:
        raise HTTPException(
            status_code=400,
            detail=(
                f"game_id={game_id!r} and as_new=true are two answers to one "
                "question; pass a target id or ask for a new one, not both"
            ),
        )

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
        # The caller's choice when given; a minted id when asked for; else the
        # bundle's own. A uuid4 cannot collide, so as_new never 409s.
        target_game_id = game_id or (str(uuid.uuid4()) if as_new else header.game_id)
        result = await repo.import_game_history(
            target_game_id, reader.records(), platform=header.platform
        )
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
        platform=header.platform,
        source_game_id=header.game_id,
        imported_events=result.imported_events,
        imported_snapshots=result.imported_snapshots,
        first_seq=result.first_seq,
        last_seq=result.last_seq,
        mode=header.mode,
        # Current rather than stale when the target is the source, so not worth
        # reporting there.
        source_id_references=(
            0 if result.game_id == header.game_id else reader.source_id_references
        ),
    )
