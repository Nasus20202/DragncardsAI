from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from eval_service.judge.actions import (
    DEFAULT_NON_STRATEGIC_ACTIONS,
    parse_action_set,
)

# Repo-level shared skills directory, resolved relative to this file
# (services/eval-service/src/eval_service/config.py -> repo root / skills).
# This is the SAME directory the agent-orchestrator discovers skills from, so a
# skill name selected in the dashboard resolves to the same file here.
#
# Only ``src/`` is copied into the container (to ``/app/src``), a shallower tree
# where ``parents[4]`` would not exist -- indexing it at import time crash-loops
# the service. Guard the lookup; the Dockerfile sets ``SKILL_ROOTS=/app/skills``
# explicitly, so this default only ever applies to the dev (repo) layout.
_MODULE_PARENTS = Path(__file__).resolve().parents
_DEFAULT_SKILL_ROOT = (
    _MODULE_PARENTS[4] / "skills" if len(_MODULE_PARENTS) > 4 else Path("skills")
)


def provider_from_model(model: str) -> str:
    """Best-effort provider id derived from a ``provider/model`` Bifrost id."""
    return model.split("/", 1)[0] if "/" in model else ""


class Settings(BaseSettings):
    """Eval-service configuration.

    Secrets (database credentials, the Bifrost judge key) only ever live in
    ``eval_database_url`` / ``bifrost_api_key`` and are never echoed by the
    health/readiness endpoints.

    ``eval_judge_model`` is REQUIRED and has NO default: the service refuses to
    evaluate (and reports readiness ``degraded``) when no judge model is
    configured, forcing a deliberate model + budget choice.
    """

    model_config = SettingsConfigDict(extra="ignore")

    eval_database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5443/eval_service",
        validation_alias=AliasChoices("eval_database_url", "EVAL_DATABASE_URL"),
    )
    history_service_base_url: str = Field(
        default="http://localhost:4004",
        validation_alias=AliasChoices(
            "history_service_base_url", "HISTORY_SERVICE_BASE_URL"
        ),
    )
    bifrost_url: str = Field(
        default="http://localhost:4003",
        validation_alias=AliasChoices("bifrost_url", "BIFROST_URL"),
    )
    bifrost_api_key: str = Field(
        default="dummy",
        validation_alias=AliasChoices("bifrost_api_key", "BIFROST_API_KEY"),
    )

    http_host: str = "0.0.0.0"
    http_port: int = 4005

    # CORS allowlist (comma-separated). The dashboard reaches eval-service via a
    # server-side proxy (not browser-direct), so a strict allowlist does NOT
    # break normal dashboard use; the default covers the local dashboard origin.
    eval_cors_allow_origins: str = Field(
        default="http://localhost:3001,http://127.0.0.1:3001",
        validation_alias=AliasChoices(
            "eval_cors_allow_origins", "EVAL_CORS_ALLOW_ORIGINS"
        ),
    )

    # Judge model is required; empty means "not configured" -> refuse to evaluate.
    eval_judge_model: str = Field(
        default="",
        validation_alias=AliasChoices("eval_judge_model", "EVAL_JUDGE_MODEL"),
    )
    eval_judge_provider: str = Field(
        default="",
        validation_alias=AliasChoices("eval_judge_provider", "EVAL_JUDGE_PROVIDER"),
    )

    # Name of the Bifrost provider-key entry judge traffic is pinned to, sent as
    # the ``x-bf-api-key`` header. This header is the ONLY thing that selects a
    # dedicated key: the ``Authorization`` bearer is gateway auth, not a key
    # selector, and Bifrost never auto-selects a ``weight: 0.0`` key. Works for
    # ANY provider that defines a key of this name (see services/bifrost).
    # Set to "" to deliberately opt out and let judge calls draw the provider's
    # normal game-playing key pool -- logged at startup, never implicit.
    eval_judge_bifrost_key_name: str = Field(
        default="eval-judge",
        validation_alias=AliasChoices(
            "eval_judge_bifrost_key_name", "EVAL_JUDGE_BIFROST_KEY_NAME"
        ),
    )
    # Recorded on every verdict and folded into the write-back idempotency key, so
    # it is how a change in what the judge is asked stays traceable. Bump it
    # whenever what the judge is SHOWN or ASKED changes, because scores from two
    # regimes are not on the same scale and must not be averaged together.
    #
    # ``eval-2`` carries two such changes: round-boundary detection was corrected
    # (a round now ends at the event that closed it, and rounds are numbered as
    # rounds of play), and a move is now judged in the context of its whole round
    # under an instruction that a play spans several actions. ``eval-1`` verdicts
    # graded a span shifted by one event at each boundary AND marked multi-action
    # plays down once per action, so they are NOT comparable to ``eval-2`` ones.
    evaluator_version: str = Field(
        default="eval-2",
        validation_alias=AliasChoices("evaluator_version", "EVALUATOR_VERSION"),
    )

    # Default reasoning configuration, used when a request omits ``judge.reasoning``.
    eval_judge_reasoning_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "eval_judge_reasoning_enabled", "EVAL_JUDGE_REASONING_ENABLED"
        ),
    )
    eval_judge_reasoning_effort: str = Field(
        default="medium",
        validation_alias=AliasChoices(
            "eval_judge_reasoning_effort", "EVAL_JUDGE_REASONING_EFFORT"
        ),
    )

    # Roots searched for selected skills, by name. ``;``- or ``,``-separated;
    # dev default is the repo-level shared ``skills/`` directory (the same one
    # the agent-orchestrator uses), so dashboard-selected names resolve here.
    skill_roots: str = Field(
        default=str(_DEFAULT_SKILL_ROOT),
        validation_alias=AliasChoices("skill_roots", "SKILL_ROOTS"),
    )

    # Retry / attempt limits.
    eval_max_attempts: int = Field(
        default=3,
        validation_alias=AliasChoices("eval_max_attempts", "EVAL_MAX_ATTEMPTS"),
    )
    eval_retry_backoff_seconds: float = Field(
        default=0.5,
        validation_alias=AliasChoices(
            "eval_retry_backoff_seconds", "EVAL_RETRY_BACKOFF_SECONDS"
        ),
    )

    # Upper bound on how many targets a single request may expand to. Caps the
    # total enqueued judge calls (each an LLM cost) so an unbounded selection
    # (whole_game / wide seq_range / huge seqs list) cannot amplify cost.
    eval_max_targets_per_request: int = Field(
        default=200,
        validation_alias=AliasChoices(
            "eval_max_targets_per_request", "EVAL_MAX_TARGETS_PER_REQUEST"
        ),
    )

    # Concurrency caps on in-flight judge calls. Enforced by the DURABLE claim
    # (``Repository.claim_pending_targets`` counts the ``running`` rows and takes
    # only the remaining capacity), never by an in-process semaphore or registry,
    # so the caps survive a restart and hold for a second worker replica.
    #
    # Per-game is 4 rather than 2 so the moves of one round actually grade in
    # parallel: a whole-game cascade at 2 was close to serial. Global stays at 8
    # as the guard against a game-wide evaluation stampeding the provider.
    eval_per_game_concurrency: int = Field(
        default=4,
        validation_alias=AliasChoices(
            "eval_per_game_concurrency", "EVAL_PER_GAME_CONCURRENCY"
        ),
    )
    eval_global_concurrency: int = Field(
        default=8,
        validation_alias=AliasChoices(
            "eval_global_concurrency", "EVAL_GLOBAL_CONCURRENCY"
        ),
    )

    # Per-evaluation token budget + judge timeout.
    eval_judge_max_tokens: int = Field(
        default=1024,
        validation_alias=AliasChoices("eval_judge_max_tokens", "EVAL_JUDGE_MAX_TOKENS"),
    )

    # Caps on the assembled judge INPUT so a large game does not blow past a
    # small-context model's window (observed live: large timelines 400 on
    # ``laguna:free``). ``eval_judge_max_state_chars`` truncates the biggest
    # content -- the per-event ``state`` JSON -- before it enters the prompt;
    # ``eval_judge_max_round_moves`` caps how many per-move blocks a round
    # prompt lists. Truncation is recorded (logged) so it stays observable.
    eval_judge_max_state_chars: int = Field(
        default=20_000,
        validation_alias=AliasChoices(
            "eval_judge_max_state_chars", "EVAL_JUDGE_MAX_STATE_CHARS"
        ),
    )
    eval_judge_max_round_moves: int = Field(
        default=100,
        validation_alias=AliasChoices(
            "eval_judge_max_round_moves", "EVAL_JUDGE_MAX_ROUND_MOVES"
        ),
    )
    # The judge model's context window, in tokens. This is what BOUNDS a skill
    # reference selection: the judge is single-shot with no tool loop, so every
    # selected byte is in the prompt, and a prompt over the window does not
    # degrade -- it is a provider error. Mirrors the agent-orchestrator's
    # ``CONTEXT_WINDOW_SIZE`` default. Set it to the window your judge model
    # actually has; that is the ONLY knob that RAISES how much reference content
    # one evaluation may carry (see eval_service.judge.reference_budget).
    #
    # Deliberately not read live from Bifrost's ``/v1/models``: eval-service's
    # judge client has no models listing, ``resolve_judge_config`` is sync, and a
    # gateway lookup in the request-REJECTION path fails a selection whenever the
    # gateway is down. See the DRA-54 design document.
    eval_judge_context_window_tokens: int = Field(
        default=128_000,
        validation_alias=AliasChoices(
            "eval_judge_context_window_tokens",
            "EVAL_JUDGE_CONTEXT_WINDOW_TOKENS",
        ),
    )
    # OPTIONAL extra cap, in characters, across the skill REFERENCE files one
    # evaluation may select. It only ever LOWERS the window-derived budget:
    #
    #   0   -- no cap beyond the window (the default)
    #   > 0 -- effective budget is min(derived, this)
    #   < 0 -- refused
    #
    # ``0`` used to mean "no budget at all". It cannot: the window bounds the
    # selection whether the setting acknowledges it or not, so that option only
    # ever chose WHERE the failure surfaced -- a clean 400 before enqueue, or a
    # provider error per target inside the worker. Raise
    # ``EVAL_JUDGE_CONTEXT_WINDOW_TOKENS`` instead.
    #
    # Unlike the truncating caps above, this one REFUSES: a clipped board is
    # still a board, but a clipped rules reference reads to the judge exactly
    # like a complete one.
    eval_judge_max_skill_reference_chars: int = Field(
        default=0,
        validation_alias=AliasChoices(
            "eval_judge_max_skill_reference_chars",
            "EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS",
        ),
    )

    # SAFETY BACKSTOPS on the per-move context window, in agent moves either side
    # of the one being graded. They are NOT the mechanism: a move is judged in the
    # context of ITS ROUND, so the window is the round and these caps only bound a
    # pathological one. The defaults are set at the same ceiling a round roll-up
    # uses (EVAL_JUDGE_MAX_ROUND_MOVES), i.e. high enough that a normal round is
    # never clipped.
    #
    # Why the round and not a small fixed count: a Marvel Champions play is
    # normally 2-4 calls (play the card, exhaust to pay the cost, assign the
    # damage) and a whole player turn runs ~6-10, so a fixed count both crosses
    # into the previous round (a different turn on a different board) and stops
    # inside the current one (hiding the rest of the play). Judging a fragment
    # against the four rubric criteria produces confidently low scores for a
    # perfectly good play -- the defect DRA-10 was filed for.
    #
    # ``EVAL_JUDGE_MOVE_CONTEXT_AFTER=0`` removes hindsight entirely.
    eval_judge_move_context_before: int = Field(
        default=100,
        validation_alias=AliasChoices(
            "eval_judge_move_context_before", "EVAL_JUDGE_MOVE_CONTEXT_BEFORE"
        ),
    )
    eval_judge_move_context_after: int = Field(
        default=100,
        validation_alias=AliasChoices(
            "eval_judge_move_context_after", "EVAL_JUDGE_MOVE_CONTEXT_AFTER"
        ),
    )
    # Per-move reasoning cap, so one verbose move cannot bloat a prompt. Applies
    # to a move prompt's neighbours AND to a round roll-up's move list -- the
    # same field either way, and the reference budget reserves against this cap,
    # so both have to honour it.
    eval_judge_move_context_reasoning_chars: int = Field(
        default=400,
        validation_alias=AliasChoices(
            "eval_judge_move_context_reasoning_chars",
            "EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS",
        ),
    )
    # Per-child rationale cap in a ROLL-UP prompt (a round's move verdicts, a
    # game's round verdicts). The rubric asks for "a short rationale paragraph",
    # so 600 chars is generous for one; the cap exists because the number of
    # children is not limited by the recording side, which made this the second
    # unbounded term in a roll-up prompt. Their COUNT is capped at
    # ``eval_judge_max_round_moves``, the same ceiling the move list uses.
    eval_judge_max_child_rationale_chars: int = Field(
        default=600,
        validation_alias=AliasChoices(
            "eval_judge_max_child_rationale_chars",
            "EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS",
        ),
    )

    # Skip evaluating recorded actions that carry no strategic decision (card
    # searches, session plumbing, pre-game setup). Skipped targets are recorded
    # as ``skipped`` with the reason, never as passed. Set false to grade
    # everything.
    eval_skip_non_strategic_moves: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "eval_skip_non_strategic_moves", "EVAL_SKIP_NON_STRATEGIC_MOVES"
        ),
    )
    # The non-strategic action names, ``,``/``;``-separated. The default is the
    # built-in taxonomy (see eval_service.judge.actions); setting this REPLACES
    # that list, so an operator states exactly which actions go ungraded. Any
    # action not listed -- including every unrecognised name -- is evaluated.
    eval_non_strategic_actions: str = Field(
        default=DEFAULT_NON_STRATEGIC_ACTIONS,
        validation_alias=AliasChoices(
            "eval_non_strategic_actions", "EVAL_NON_STRATEGIC_ACTIONS"
        ),
    )
    eval_judge_timeout_seconds: float = Field(
        default=120.0,
        validation_alias=AliasChoices(
            "eval_judge_timeout_seconds", "EVAL_JUDGE_TIMEOUT_SECONDS"
        ),
    )

    # History read pagination page size.
    history_page_size: int = Field(
        default=1000,
        validation_alias=AliasChoices("history_page_size", "HISTORY_PAGE_SIZE"),
    )

    @property
    def cors_allow_origins(self) -> list[str]:
        """Configured CORS origins as a list (comma-separated, trimmed)."""
        return [o.strip() for o in self.eval_cors_allow_origins.split(",") if o.strip()]

    @property
    def judge_configured(self) -> bool:
        """True when a judge model has been deliberately configured."""
        return bool(self.eval_judge_model.strip())

    @property
    def judge_routing_provider(self) -> str:
        """Bifrost provider the DEFAULT judge model routes to.

        Bifrost routes on the ``provider/model`` prefix of the model id, so that
        prefix -- not ``EVAL_JUDGE_PROVIDER``, which is verdict metadata --
        decides whose key pool is drawn. Falls back to the explicit provider
        setting when the model id carries no prefix. Empty when neither is set.
        """
        return provider_from_model(self.eval_judge_model.strip()) or (
            self.eval_judge_provider.strip()
        )

    @property
    def non_strategic_actions(self) -> frozenset[str]:
        """Action names to skip as non-strategic (empty when skipping is off)."""
        if not self.eval_skip_non_strategic_moves:
            return frozenset()
        return parse_action_set(self.eval_non_strategic_actions)

    @property
    def skill_root_paths(self) -> tuple[Path, ...]:
        """Configured skill roots as a tuple of Paths (``;``/``,`` separated)."""
        raw = self.skill_roots.replace(";", ",")
        return tuple(Path(part.strip()) for part in raw.split(",") if part.strip())

    @field_validator("eval_judge_reasoning_effort")
    @classmethod
    def validate_reasoning_effort(cls, value: str) -> str:
        if value not in ("low", "medium", "high"):
            raise ValueError("eval_judge_reasoning_effort must be low|medium|high")
        return value

    @field_validator("http_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("http_port must be a valid TCP port")
        return value

    @field_validator("eval_max_attempts")
    @classmethod
    def validate_max_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_max_attempts must be at least 1")
        return value

    @field_validator("eval_retry_backoff_seconds")
    @classmethod
    def validate_backoff(cls, value: float) -> float:
        if value < 0:
            raise ValueError("eval_retry_backoff_seconds must be non-negative")
        return value

    @field_validator("eval_per_game_concurrency", "eval_global_concurrency")
    @classmethod
    def validate_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("concurrency caps must be at least 1")
        return value

    @field_validator("eval_max_targets_per_request")
    @classmethod
    def validate_max_targets(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_max_targets_per_request must be at least 1")
        return value

    @field_validator("eval_judge_max_tokens")
    @classmethod
    def validate_max_tokens(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_judge_max_tokens must be at least 1")
        return value

    @field_validator("eval_judge_max_skill_reference_chars")
    @classmethod
    def validate_max_skill_reference_chars(cls, value: int) -> int:
        # ``0`` deliberately means "no cap beyond the context window"; a NEGATIVE
        # value would read the same way (the check is ``> 0``) while reading like
        # a tight limit. Refuse it rather than silently ignoring an operator who
        # meant to restrict the selection.
        if value < 0:
            raise ValueError(
                "eval_judge_max_skill_reference_chars must be >= 0 "
                "(0 = no cap beyond the context window)"
            )
        return value

    @field_validator("eval_judge_context_window_tokens")
    @classmethod
    def validate_context_window_tokens(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_judge_context_window_tokens must be at least 1")
        return value

    @field_validator("eval_judge_max_state_chars")
    @classmethod
    def validate_max_state_chars(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_judge_max_state_chars must be at least 1")
        return value

    @field_validator("eval_judge_max_round_moves")
    @classmethod
    def validate_max_round_moves(cls, value: int) -> int:
        if value < 1:
            raise ValueError("eval_judge_max_round_moves must be at least 1")
        return value

    @field_validator(
        "eval_judge_move_context_before",
        "eval_judge_move_context_after",
        "eval_judge_move_context_reasoning_chars",
    )
    @classmethod
    def validate_move_context(cls, value: int) -> int:
        if value < 0:
            raise ValueError("move-context window sizes must be non-negative")
        return value

    @field_validator("eval_judge_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("eval_judge_timeout_seconds must be positive")
        return value

    @field_validator("history_page_size")
    @classmethod
    def validate_page_size(cls, value: int) -> int:
        if not 1 <= value <= 1000:
            raise ValueError("history_page_size must be between 1 and 1000")
        return value
