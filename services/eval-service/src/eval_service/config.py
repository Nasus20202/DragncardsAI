from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-level shared skills directory, resolved relative to this file
# (services/eval-service/src/eval_service/config.py -> repo root / skills).
# This is the SAME directory the agent-orchestrator discovers skills from, so a
# skill name selected in the dashboard resolves to the same file here.
_DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[4] / "skills"


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
    evaluator_version: str = Field(
        default="eval-1",
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

    # Concurrency caps on in-flight judge calls.
    eval_per_game_concurrency: int = Field(
        default=2,
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
