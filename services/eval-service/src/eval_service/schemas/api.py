from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from eval_service.schemas.verdict import Scope, VerdictPayload

# Terminal/non-terminal target statuses shared across response models. A target
# is non-terminal while ``pending`` or ``running``; the rest are terminal.
TargetStatus = Literal[
    "pending", "running", "completed", "skipped", "failed", "cancelled"
]
# Request-level aggregate statuses derived from a request's target statuses.
RequestStatus = Literal["pending", "completed", "partial", "failed", "cancelled"]

MAX_SKILLS = 32
# Ceilings on attacker-influenced judge-config fields so a single request can't
# amplify per-target LLM cost / storage without bound.
MAX_PROMPT_OVERRIDE = 50_000
MAX_REASONING_TOKENS = 200_000

# Absolute, schema-level ceilings so an absurd selection is rejected early
# (HTTP 422) before any history read or expansion. The precise per-request cap
# on the EXPANDED target count is enforced separately from configuration.
MAX_SELECTION_LIST = 1000
MAX_SEQ_RANGE_SPAN = 100_000


class SeqRange(BaseModel):
    from_seq: int = Field(ge=1)
    to_seq: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "SeqRange":
        if self.to_seq < self.from_seq:
            raise ValueError("seq_range.to_seq must be >= from_seq")
        if self.to_seq - self.from_seq + 1 > MAX_SEQ_RANGE_SPAN:
            raise ValueError(f"seq_range span must not exceed {MAX_SEQ_RANGE_SPAN}")
        return self


class Selection(BaseModel):
    """A target selection. At least one field must be provided."""

    seqs: list[int] | None = Field(default=None, max_length=MAX_SELECTION_LIST)
    rounds: list[int] | None = Field(default=None, max_length=MAX_SELECTION_LIST)
    seq_range: SeqRange | None = None
    whole_game: bool = False

    @model_validator(mode="after")
    def validate_non_empty(self) -> "Selection":
        if not (self.seqs or self.rounds or self.seq_range or self.whole_game):
            raise ValueError(
                "selection must specify at least one of: seqs, rounds, "
                "seq_range, whole_game"
            )
        return self


class JudgeReasoning(BaseModel):
    """Per-evaluation reasoning controls (mirrors the Play config shape)."""

    enabled: bool = False
    effort: Literal["low", "medium", "high"] = "medium"
    # Optional reasoning token budget; positive integer (bounded) when provided.
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_REASONING_TOKENS)


class JudgeConfig(BaseModel):
    """Optional per-evaluation judge overrides. All fields are optional;
    omitted fields fall back to the server (env) defaults."""

    provider_id: str | None = None
    # Full Bifrost ``provider/model`` id, like the default ``EVAL_JUDGE_MODEL``.
    model_name: str | None = None
    reasoning: JudgeReasoning | None = None
    prompt_override: str | None = Field(default=None, max_length=MAX_PROMPT_OVERRIDE)
    # Skill NAMES (resolved to skill content under SKILL_ROOTS).
    skills: list[str] | None = Field(default=None, max_length=MAX_SKILLS)


class EvaluationRequestBody(BaseModel):
    scope: Scope
    selection: Selection
    force: bool = False
    judge: JudgeConfig | None = None


class TargetSummary(BaseModel):
    target_seq: int
    scope: Scope
    round_span: list[int] | None = None
    # The player this target scores (e.g. ``player1``); None for legacy targets
    # that predate per-player scoring. Move targets carry their acting player;
    # round/game targets carry the player whose contributions they score.
    player: str | None = None
    status: TargetStatus


class CreateEvaluationResponse(BaseModel):
    request_id: str
    game_id: str
    scope: Scope
    created_count: int
    skipped_count: int
    targets: list[TargetSummary]


class TargetResult(BaseModel):
    target_seq: int
    scope: Scope
    round_span: list[int] | None = None
    # The player this target scores (mirrors ``TargetSummary.player``); also
    # surfaced on the nested ``verdict`` payload.
    player: str | None = None
    status: TargetStatus
    verdict: VerdictPayload | None = None
    error: str | None = None


class RequestStatusResponse(BaseModel):
    request_id: str
    game_id: str
    status: RequestStatus
    targets: list[TargetResult]


class CancelResponse(BaseModel):
    request_id: str
    cancelled: int


class EvaluationListItem(BaseModel):
    """One row in the cross-game evaluations queue: a request summary with its
    creation time and per-target results (same shape as ``RequestStatusResponse``
    plus ``created_at``)."""

    request_id: str
    game_id: str
    status: RequestStatus
    created_at: datetime
    targets: list[TargetResult]


class EvaluationListResponse(BaseModel):
    requests: list[EvaluationListItem]


class ClearEvaluationsResponse(BaseModel):
    """Result of clearing all fully-terminal evaluation requests."""

    deleted_count: int
