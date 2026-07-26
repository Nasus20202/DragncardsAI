from __future__ import annotations

import json
import re
from typing import Any

from eval_service.schemas.verdict import (
    EvaluatorMeta,
    Scope,
    VerdictPayload,
    VerdictScores,
)


class VerdictParseError(Exception):
    """Raised when the judge response cannot be parsed into a structured verdict."""


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
# A fenced code block, optionally language-hinted (```json ... ```), capturing
# only the inner body so backticks inside the JSON are never stripped.
_FENCE_RE = re.compile(
    r"```[ \t]*[a-zA-Z0-9_-]*[ \t]*\r?\n(?P<body>.*?)\r?\n?```",
    re.DOTALL,
)


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # Unwrap a fenced ```json ... ``` block if present, keeping only its body.
    fence = _FENCE_RE.search(text)
    if fence is not None:
        text = fence.group("body").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_OBJECT_RE.search(text)
        if match is None:
            raise VerdictParseError("no JSON object found in judge response")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise VerdictParseError(f"invalid JSON in judge response: {exc}") from exc


def _clamp_score(value: Any) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError) as exc:
        raise VerdictParseError(f"non-numeric score: {value!r}") from exc
    return max(0, min(10, number))


def parse_verdict(
    response_text: str,
    *,
    scope: Scope,
    target_seq: int,
    round_span: list[int] | None,
    model: str,
    provider: str,
    evaluator_version: str,
    player: str | None = None,
) -> VerdictPayload:
    """Parse a judge response into a structured :class:`VerdictPayload`.

    Scores are clamped to the 0-10 range. Missing scores raise rather than
    silently default, so a malformed verdict is treated as a judge failure.
    """
    data = _extract_json(response_text)
    raw_scores = data.get("scores")
    if not isinstance(raw_scores, dict):
        raise VerdictParseError("judge response missing a scores object")

    required = (
        "rules_legality",
        "strategic_quality",
        "tempo_efficiency",
        "threat_resource",
    )
    for key in required:
        if key not in raw_scores:
            raise VerdictParseError(f"judge response missing score {key!r}")

    scores = VerdictScores(
        rules_legality=_clamp_score(raw_scores["rules_legality"]),
        strategic_quality=_clamp_score(raw_scores["strategic_quality"]),
        tempo_efficiency=_clamp_score(raw_scores["tempo_efficiency"]),
        threat_resource=_clamp_score(raw_scores["threat_resource"]),
    )

    if "overall_score" not in data:
        raise VerdictParseError("judge response missing overall_score")
    overall = _clamp_score(data["overall_score"])

    rationale = str(data.get("rationale") or "")
    flags_raw = data.get("flags") or []
    flags = [str(f) for f in flags_raw] if isinstance(flags_raw, list) else []

    return VerdictPayload(
        scope=scope,
        target_seq=target_seq,
        round_span=round_span,
        player=player,
        scores=scores,
        overall_score=overall,
        rationale=rationale,
        flags=flags,
        evaluator=EvaluatorMeta(
            model=model,
            provider=provider,
            evaluator_version=evaluator_version,
        ),
    )
