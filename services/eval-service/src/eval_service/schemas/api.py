from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    Field,
    StringConstraints,
    model_validator,
)

from eval_service.schemas.base import StrictRequest
from eval_service.schemas.verdict import Scope, VerdictPayload
from eval_service.schemas.history import PLATFORM_DRAGNCARDS, Platform

# Terminal/non-terminal target statuses shared across response models. A target
# is non-terminal while ``pending`` or ``running``; the rest are terminal.
TargetStatus = Literal[
    "pending", "running", "completed", "skipped", "failed", "cancelled"
]
# Request-level aggregate statuses derived from a request's target statuses.
RequestStatus = Literal["pending", "completed", "partial", "failed", "cancelled"]

MAX_SKILLS = 32
# NOT a selection policy. A count measures nothing here: the shipped rules skill
# spans a 20x size range across its files (~38.5k chars down to under 2k), so any
# count bound refuses selections it should allow and admits ones it should refuse.
# The real bound is the SIZE budget derived from the judge model's context window
# at resolve time (eval_service.judge.reference_budget).
#
# What this ceiling is for is rejecting an absurd request BODY before anything is
# read from disk -- 100k selection strings would be 100k parses and file reads
# before the budget could trip. It sits at MAX_SELECTION_LIST's scale for exactly
# that reason, and is unreachable by any selection over the 28 reference files
# that ship: "select all" is 28.
MAX_SKILL_REFERENCES = 1_000
# Per-ENTRY ceiling: "<skill-name>/<relative-path>.md". Generous for a real path.
MAX_SKILL_REFERENCE_LENGTH = 512
# Ceilings on attacker-influenced judge-config fields so a single request can't
# amplify per-target LLM cost / storage without bound.
MAX_PROMPT_OVERRIDE = 50_000
MAX_REASONING_TOKENS = 200_000

# Absolute, schema-level ceilings so an absurd selection is rejected early
# (HTTP 422) before any history read or expansion. The precise per-request cap
# on the EXPANDED target count is enforced separately from configuration.
MAX_SELECTION_LIST = 1000
MAX_SEQ_RANGE_SPAN = 100_000


class SeqRange(StrictRequest):
    from_seq: int = Field(ge=1)
    to_seq: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> "SeqRange":
        if self.to_seq < self.from_seq:
            raise ValueError("seq_range.to_seq must be >= from_seq")
        if self.to_seq - self.from_seq + 1 > MAX_SEQ_RANGE_SPAN:
            raise ValueError(f"seq_range span must not exceed {MAX_SEQ_RANGE_SPAN}")
        return self


class Selection(StrictRequest):
    """A target selection. At least one field must be provided."""

    seqs: list[int] | None = Field(default=None, max_length=MAX_SELECTION_LIST)
    # Rounds of PLAY, 1-based (the numbers the History tab shows), NOT the raw
    # DragnCards ``roundNumber``, which counts completed rounds.
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


class RoundSummary(BaseModel):
    """One detected round, as offered to a client picking rounds to evaluate."""

    # The 1-based round OF PLAY, which is exactly what ``Selection.rounds``
    # accepts, so a client echoes it back untranslated. NOT DragnCards' raw
    # ``roundNumber``, which counts COMPLETED rounds and reads 0 for the first
    # round of play; ``detect_round_boundaries`` has already converted it.
    round_number: int
    # Presentation label built from ``round_number`` ("Round 1").
    label: str
    from_seq: int
    to_seq: int
    # Agent moves recorded in the span, so a client can show how much a round
    # holds -- and tell an empty round from a busy one -- before selecting it.
    move_count: int
    # Players who made an agent move in the span; empty when none did.
    players: list[str] = Field(default_factory=list)


class RoundListResponse(BaseModel):
    game_id: str
    rounds: list[RoundSummary]


class JudgeReasoning(StrictRequest):
    """Per-evaluation reasoning controls (mirrors the Play config shape)."""

    enabled: bool = False
    effort: str = "medium"
    # Optional reasoning token budget; positive integer (bounded) when provided.
    max_tokens: int | None = Field(default=None, ge=1, le=MAX_REASONING_TOKENS)


class JudgeConfig(StrictRequest):
    """Optional per-evaluation judge overrides. All fields are optional;
    omitted fields fall back to the server (env) defaults."""

    provider_id: str | None = None
    # Full Bifrost ``provider/model`` id, like the default ``EVAL_JUDGE_MODEL``.
    model_name: str | None = None
    reasoning: JudgeReasoning | None = None
    prompt_override: str | None = Field(default=None, max_length=MAX_PROMPT_OVERRIDE)
    # Skill NAMES (resolved to skill content under SKILL_ROOTS).
    skills: list[str] | None = Field(default=None, max_length=MAX_SKILLS)
    # Skill REFERENCE files, each ``"<skill-name>/<relative-path>.md"`` -- the two
    # coordinates the agent-orchestrator's ``load_skill_reference`` takes, joined.
    # A reference may be selected WITHOUT its skill's SKILL.md: "give the judge
    # only the errata" is a legitimate configuration, and charging it the whole
    # skill to reach one file would be an arbitrary tax.
    # Per-ENTRY length too, not only the list length: a reference path is a skill
    # name plus a relative path, so a few hundred characters is generous, and the
    # list ceiling is now 1,000 rather than 8.
    skill_references: (
        list[Annotated[str, StringConstraints(max_length=MAX_SKILL_REFERENCE_LENGTH)]]
        | None
    ) = Field(default=None, max_length=MAX_SKILL_REFERENCES)


class EvaluationRequestBody(StrictRequest):
    platform: Platform | None = None
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
