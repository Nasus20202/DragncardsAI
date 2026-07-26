from __future__ import annotations

from eval_service.schemas.api import TargetResult
from eval_service.schemas.verdict import VerdictPayload
from eval_service.storage.models import NON_TERMINAL_STATUSES, EvaluatedTargetRow

# Non-terminal target statuses: the request is still in progress while any
# target is pending or running. Canonical definition lives in storage.models so
# the listing query and this aggregation never drift apart.
_NON_TERMINAL = NON_TERMINAL_STATUSES


def to_target_result(row: EvaluatedTargetRow) -> TargetResult:
    round_span = (
        [row.round_from_seq, row.round_to_seq]
        if row.round_from_seq is not None and row.round_to_seq is not None
        else None
    )
    verdict = (
        VerdictPayload.model_validate(row.verdict_json)
        if row.verdict_json is not None
        else None
    )
    return TargetResult(
        target_seq=row.target_seq,
        scope=row.scope,  # type: ignore[arg-type]
        round_span=round_span,
        player=row.player or None,
        status=row.status,  # type: ignore[arg-type]
        verdict=verdict,
        error=row.error,
    )


def request_status(targets: list[EvaluatedTargetRow]) -> str:
    """Derive the request-level status from its targets.

    * ``pending`` while any target is still non-terminal (pending/running);
    * once all are terminal: ``completed`` if every target succeeded;
      ``cancelled`` if any target was cancelled and none failed;
      ``failed`` if none succeeded;
      otherwise ``partial`` (a mix of succeeded and skipped/failed/cancelled).
    """
    if not targets:
        return "completed"
    if any(t.status in _NON_TERMINAL for t in targets):
        return "pending"
    statuses = [t.status for t in targets]
    succeeded = sum(1 for s in statuses if s == "completed")
    if succeeded == len(statuses):
        return "completed"
    any_cancelled = any(s == "cancelled" for s in statuses)
    any_failed = any(s == "failed" for s in statuses)
    if any_cancelled and not any_failed:
        return "cancelled"
    if succeeded == 0:
        return "failed"
    return "partial"
