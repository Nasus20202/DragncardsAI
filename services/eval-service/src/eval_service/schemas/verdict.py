from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Scope = Literal["move", "round", "game"]


class VerdictScores(BaseModel):
    """Per-criterion judge scores, each on a 0-10 integer scale."""

    rules_legality: int = Field(ge=0, le=10)
    strategic_quality: int = Field(ge=0, le=10)
    tempo_efficiency: int = Field(ge=0, le=10)
    threat_resource: int = Field(ge=0, le=10)


class EvaluatorMeta(BaseModel):
    model: str
    provider: str
    evaluator_version: str


class VerdictPayload(BaseModel):
    """The ``evaluator`` history event payload.

    MUST match the dashboard ``HistoryEvaluatorPayload`` shape exactly.
    """

    scope: Scope
    target_seq: int
    round_span: list[int] | None = None
    # The player this verdict pertains to (e.g. ``player1``). Optional for
    # backward compatibility with move/round verdicts that predate per-player
    # scoring; per-player round/game verdicts always carry it.
    player: str | None = None
    scores: VerdictScores
    overall_score: int = Field(ge=0, le=10)
    rationale: str
    flags: list[str] = Field(default_factory=list)
    evaluator: EvaluatorMeta
