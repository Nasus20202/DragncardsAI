from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from eval_service.judge.config import ResolvedJudgeConfig
from eval_service.schemas.verdict import VerdictPayload

ENVELOPE_VERSION = 1
ACTOR = "evaluator"
EVENT_TYPE = "evaluation"


def judge_config_digest(config: ResolvedJudgeConfig | None) -> str:
    """Stable, deterministic hash of the resolved judge config.

    Folds in every dimension that changes a verdict's meaning
    (model/provider/reasoning/prompt_override/skills/skill_references) so two
    evaluations under DIFFERENT judge configurations produce different
    idempotency keys, while an identical re-evaluation produces the same key.
    ``None`` (no per-request config) hashes to a stable sentinel so legacy
    callers stay deterministic.

    A config that selects no references hashes exactly as it did before
    references existed: ``to_json`` omits the key entirely when it is empty, so
    every already-recorded verdict still deduplicates against a re-run.
    """
    if config is None:
        raw = "none"
    else:
        # ``sort_keys`` sorts dict KEYS but not list ELEMENTS, so the selection
        # lists are sorted explicitly here: the same skill (or reference) set in a
        # different order is semantically identical and MUST hash the same,
        # otherwise a re-eval with a reordered selection would spuriously produce
        # a second history event. Only the digest copy is sorted; the
        # stored/injected order is untouched.
        payload = config.to_json()
        payload["skills"] = sorted(payload.get("skills") or [])
        if "skill_references" in payload:
            payload["skill_references"] = sorted(payload["skill_references"])
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def verdict_idempotency_key(
    game_id: str,
    target_seq: int,
    scope: str,
    evaluator_version: str,
    config: ResolvedJudgeConfig | None = None,
    player: str | None = None,
) -> str:
    """sha256(game_id|target_seq|scope|player|evaluator_version|config_digest).

    The resolved-judge-config digest is part of the key so a forced re-eval
    under a DIFFERENT judge config (model/provider/prompt/skills/reasoning)
    yields a distinct history event instead of being silently deduped by the
    history-service's ``on_conflict_do_nothing``, while an identical re-eval
    still dedupes. ``player`` is folded in so per-player round/game roll-ups that
    share a closing ``target_seq`` (one per acting player) each get a distinct
    history event. The key stays fully deterministic.
    """
    raw = (
        f"{game_id}|{target_seq}|{scope}|{player or ''}|{evaluator_version}"
        f"|{judge_config_digest(config)}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_verdict_envelope(
    game_id: str,
    verdict: VerdictPayload,
    config: ResolvedJudgeConfig | None = None,
) -> dict:
    """Build the ``evaluator`` history envelope carrying a verdict payload.

    ``seq`` and ``recorded_at`` are assigned by the history-service at commit
    time and are intentionally omitted here. ``producer_offset`` is also
    omitted by design: evaluator verdicts are advisory events, not part of the
    replayable game stream, so they carry no producer offset.

    ``config`` is the resolved judge config used for this evaluation; it is
    folded into the idempotency key so a re-eval under different judge settings
    is not deduped against the prior verdict.
    """
    return {
        "envelope_version": ENVELOPE_VERSION,
        "event_id": str(uuid.uuid4()),
        "game_id": game_id,
        "actor": ACTOR,
        "event_type": EVENT_TYPE,
        "payload": verdict.model_dump(),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": verdict_idempotency_key(
            game_id,
            verdict.target_seq,
            verdict.scope,
            verdict.evaluator.evaluator_version,
            config,
            verdict.player,
        ),
    }
