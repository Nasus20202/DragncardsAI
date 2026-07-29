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
    # The SEQUENCE span this verdict covers, ``[from_seq, to_seq]`` — event seqs
    # on the game timeline, NOT round numbers. It is what seq-correlates a
    # round/game verdict to the events it graded. Reading its two elements as
    # round numbers labels the first round of a real game "Rounds 1-63"; the round
    # to name is ``round_number`` below.
    round_span: list[int] | None = None
    # The 1-based round of PLAY this verdict grades (``assembly.round_of_play``,
    # i.e. DragnCards' completed-round counter + 1) — the same number the History
    # transcript and ``GET /games/{id}/rounds`` name a round by. Set for
    # ``scope=round`` only: a move is named by its own seq and a game verdict spans
    # every round, so neither has one round to name. ``None`` on a verdict recorded
    # before this field existed, which a consumer labels without a round number
    # rather than deriving one from ``round_span``.
    round_number: int | None = None
    # The player this verdict pertains to (e.g. ``player1``). Optional for
    # backward compatibility with move/round verdicts that predate per-player
    # scoring; per-player round/game verdicts always carry it.
    player: str | None = None
    scores: VerdictScores
    overall_score: int = Field(ge=0, le=10)
    rationale: str
    flags: list[str] = Field(default_factory=list)
    evaluator: EvaluatorMeta
