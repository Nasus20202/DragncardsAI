from __future__ import annotations

from functools import cached_property
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REQUIRED_PROVIDER_IDS = (
    "nvidia",
    "openrouter",
    "mistral",
    "claude",
    "openai",
    "lmstudio",
    "gemini",
    "opencodego",
)

# How much text one tool call's arguments or one tool result may contribute to a
# compaction input. Measured against real sessions: a full simplified Marvel
# Champions board (`get_game_state`) runs to ~6.3k characters at the 99th
# percentile, while a card search, an action list or a raw game state reach 50k
# to 500k. This sits well above the board that must survive intact and well
# below the payloads that have to be cut.
COMPACTION_EVENT_CHAR_BUDGET_DEFAULT = 20_000

# The smallest span a compaction is allowed to be attempted on, in estimated
# tokens, when no previous summary exists to measure against. Compaction can
# only shrink the replayed history, so once the system prompt, the tool
# definitions and an inlined skill count toward the trigger, a session can sit
# above the threshold with almost no history — and summarizing it would cost a
# blocking model call that cannot lower the ratio. Below this floor the trigger
# reports fixed request cost as the cause and does not call the summarizer.
#
# The floor is a stand-in for "the summary would not be smaller than the
# history it replaces". Once a session has a `CompactionRecord`, the measured
# token length of its most recent summary is used instead and the floor stops
# applying. 4000 tokens is about 3% of the default 128k window and about the
# size of one mid-sized inlined `SKILL.md`; no session in the deployment has
# compacted yet, so it is chosen to be revised from the first real summaries
# rather than defended as measured.
#
# Setting it near or above a model's context window disables automatic
# compaction for sessions that have never compacted, since no span can clear
# it. It is not bounded here because the real window is whatever the provider
# reports for the session's model, which this constant cannot know.
COMPACTION_MIN_REPLAY_TOKENS_DEFAULT = 4_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5441/agent_orchestrator"
    )
    bifrost_url: str = "http://localhost:4003"
    bifrost_api_key: str = "dummy"
    http_host: str = "0.0.0.0"
    http_port: int = 4002
    skill_roots_raw: str = Field(
        default="../../skills",
        validation_alias=AliasChoices("skill_roots_raw", "SKILL_ROOTS"),
    )
    worker_poll_interval_seconds: float = 0.2
    # How long an idle SSE job-event stream waits on the live event bus before
    # re-reading the job's status from the database. Deliberately not
    # `worker_poll_interval_seconds`: that value is tuned for how quickly the
    # worker claims a queued job from PostgreSQL, and reusing it here made every
    # open stream issue five blocking Valkey reads and ten database queries a
    # second for the whole life of a job. A published event ends the wait at
    # once, so this only bounds the rare case of a job going terminal without
    # publishing anything.
    job_event_stream_idle_block_seconds: float = Field(
        default=15.0,
        validation_alias=AliasChoices(
            "job_event_stream_idle_block_seconds",
            "JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS",
        ),
    )
    worker_max_tool_rounds: int = 64
    default_job_max_attempts: int = 2
    subagent_wait_timeout_seconds: float = 600.0
    subagent_wait_poll_interval_seconds: float = 5.0
    ask_user_timeout_seconds: float = 600.0
    ask_user_poll_interval_seconds: float = 2.0
    game_service_mcp_url: str = Field(
        default="http://localhost:4001/mcp/",
        validation_alias=AliasChoices("game_service_mcp_url", "GAME_SERVICE_MCP_URL"),
    )
    default_game_service_mcp_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "default_game_service_mcp_enabled", "DEFAULT_GAME_SERVICE_MCP_ENABLED"
        ),
    )
    default_game_service_mcp_name: str = Field(
        default="game-service",
        validation_alias=AliasChoices(
            "default_game_service_mcp_name", "DEFAULT_GAME_SERVICE_MCP_NAME"
        ),
    )
    default_game_service_mcp_transport: str = Field(
        default="streamable-http",
        validation_alias=AliasChoices(
            "default_game_service_mcp_transport", "DEFAULT_GAME_SERVICE_MCP_TRANSPORT"
        ),
    )
    valkey_url: str = "redis://localhost:6381/0"
    # Shared Valkey carrying the history:ingest bus. All three services
    # (game-service, agent-orchestrator, history-service) MUST reach the same
    # instance. Defaults to this service's own valkey_url, which is the shared
    # history bus by decision.
    history_valkey_url: str = Field(
        default="",
        validation_alias=AliasChoices("history_valkey_url", "HISTORY_VALKEY_URL"),
    )
    history_ingest_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "history_ingest_enabled", "HISTORY_INGEST_ENABLED"
        ),
    )
    history_ingest_stream: str = Field(
        default="history:ingest",
        validation_alias=AliasChoices("history_ingest_stream", "HISTORY_INGEST_STREAM"),
    )
    history_ingest_stream_maxlen: int = Field(
        default=100_000,
        validation_alias=AliasChoices(
            "history_ingest_stream_maxlen", "HISTORY_INGEST_STREAM_MAXLEN"
        ),
    )
    mcp_request_timeout_seconds: float = 30.0
    provider_models_cache_ttl_seconds: float = 600.0
    bifrost_list_models_timeout_seconds: float = Field(
        default=8.0,
        validation_alias=AliasChoices(
            "bifrost_list_models_timeout_seconds",
            "BIFROST_LIST_MODELS_TIMEOUT_SECONDS",
        ),
    )
    bifrost_unavailable_cache_ttl_seconds: float = Field(
        default=600.0,
        validation_alias=AliasChoices(
            "bifrost_unavailable_cache_ttl_seconds",
            "BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS",
        ),
    )
    bifrost_unavailable_retryable_cache_ttl_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices(
            "bifrost_unavailable_retryable_cache_ttl_seconds",
            "BIFROST_UNAVAILABLE_RETRYABLE_CACHE_TTL_SECONDS",
        ),
    )
    max_request_body_bytes: int = Field(
        default=8 * 1024 * 1024,
        validation_alias=AliasChoices(
            "max_request_body_bytes", "MAX_REQUEST_BODY_BYTES"
        ),
    )
    # CORS allowlist (comma-separated). The dashboard reaches the orchestrator via
    # a server-side proxy (not browser-direct), so a strict allowlist does NOT
    # break normal dashboard use; the default covers the local dashboard origin.
    # This must never widen back to "*": Compose publishes 4002 on the host, so a
    # wildcard lets ANY page a developer visits drive DELETE /sessions/{id} and
    # POST /sessions/{id}/prompts from the browser — destroying agent sessions and
    # spending the owner's model budget.
    cors_allow_origins_raw: str = Field(
        default="http://localhost:3001,http://127.0.0.1:3001",
        validation_alias=AliasChoices("cors_allow_origins_raw", "CORS_ALLOW_ORIGINS"),
    )
    supported_provider_ids: tuple[str, ...] = REQUIRED_PROVIDER_IDS
    context_window_size: int = Field(
        default=128000,
        validation_alias=AliasChoices("context_window_size", "CONTEXT_WINDOW_SIZE"),
    )
    context_compaction_threshold: float = Field(
        default=0.8,
        validation_alias=AliasChoices(
            "context_compaction_threshold", "CONTEXT_COMPACTION_THRESHOLD"
        ),
    )
    context_compaction_event_char_budget: int = Field(
        default=COMPACTION_EVENT_CHAR_BUDGET_DEFAULT,
        validation_alias=AliasChoices(
            "context_compaction_event_char_budget",
            "CONTEXT_COMPACTION_EVENT_CHAR_BUDGET",
        ),
    )
    context_compaction_min_replay_tokens: int = Field(
        default=COMPACTION_MIN_REPLAY_TOKENS_DEFAULT,
        validation_alias=AliasChoices(
            "context_compaction_min_replay_tokens",
            "CONTEXT_COMPACTION_MIN_REPLAY_TOKENS",
        ),
    )
    enabled_provider_ids_raw: str = Field(
        default=",".join(REQUIRED_PROVIDER_IDS),
        validation_alias=AliasChoices(
            "enabled_provider_ids_raw",
            "ENABLED_PROVIDER_IDS",
        ),
    )

    @field_validator("worker_poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("worker_poll_interval_seconds must be positive")
        return value

    @field_validator("job_event_stream_idle_block_seconds")
    @classmethod
    def validate_job_event_stream_idle_block(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("job_event_stream_idle_block_seconds must be positive")
        return value

    @field_validator("worker_max_tool_rounds")
    @classmethod
    def validate_tool_rounds(cls, value: int) -> int:
        if value < 1:
            raise ValueError("worker_max_tool_rounds must be at least 1")
        return value

    @field_validator("default_job_max_attempts")
    @classmethod
    def validate_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("default_job_max_attempts must be at least 1")
        return value

    @field_validator("context_compaction_event_char_budget")
    @classmethod
    def validate_compaction_event_char_budget(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("context_compaction_event_char_budget must be positive")
        return value

    @field_validator("context_compaction_min_replay_tokens")
    @classmethod
    def validate_compaction_min_replay_tokens(cls, value: int) -> int:
        if value < 0:
            raise ValueError(
                "context_compaction_min_replay_tokens must not be negative"
            )
        return value

    @field_validator("subagent_wait_timeout_seconds")
    @classmethod
    def validate_subagent_wait_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("subagent_wait_timeout_seconds must be positive")
        return value

    @field_validator("subagent_wait_poll_interval_seconds")
    @classmethod
    def validate_subagent_wait_poll_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("subagent_wait_poll_interval_seconds must be positive")
        return value

    @field_validator("ask_user_timeout_seconds")
    @classmethod
    def validate_ask_user_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ask_user_timeout_seconds must be positive")
        return value

    @field_validator("ask_user_poll_interval_seconds")
    @classmethod
    def validate_ask_user_poll_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("ask_user_poll_interval_seconds must be positive")
        return value

    @field_validator("provider_models_cache_ttl_seconds")
    @classmethod
    def validate_provider_models_cache_ttl(cls, value: float) -> float:
        if value < 0:
            raise ValueError("provider_models_cache_ttl_seconds must be non-negative")
        return value

    @field_validator("bifrost_list_models_timeout_seconds")
    @classmethod
    def validate_bifrost_list_models_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("bifrost_list_models_timeout_seconds must be positive")
        return value

    @field_validator("bifrost_unavailable_cache_ttl_seconds")
    @classmethod
    def validate_bifrost_unavailable_cache_ttl(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("bifrost_unavailable_cache_ttl_seconds must be positive")
        return value

    @field_validator("bifrost_unavailable_retryable_cache_ttl_seconds")
    @classmethod
    def validate_bifrost_unavailable_retryable_cache_ttl(cls, value: float) -> float:
        if value <= 0:
            raise ValueError(
                "bifrost_unavailable_retryable_cache_ttl_seconds must be positive"
            )
        return value

    @field_validator("max_request_body_bytes")
    @classmethod
    def validate_max_request_body_bytes(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_request_body_bytes must be at least 1")
        return value

    @field_validator("history_ingest_stream_maxlen")
    @classmethod
    def validate_history_ingest_stream_maxlen(cls, value: int) -> int:
        if value < 1:
            raise ValueError("history_ingest_stream_maxlen must be at least 1")
        return value

    @field_validator("supported_provider_ids")
    @classmethod
    def validate_providers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        missing = sorted(set(REQUIRED_PROVIDER_IDS) - set(value))
        if missing:
            raise ValueError(f"missing provider ids: {', '.join(missing)}")
        return value

    @property
    def cors_allow_origins(self) -> list[str]:
        """Configured CORS origins as a list (comma-separated, trimmed)."""
        return [o.strip() for o in self.cors_allow_origins_raw.split(",") if o.strip()]

    @property
    def effective_history_valkey_url(self) -> str:
        """Valkey URL for the shared history:ingest bus.

        Falls back to ``valkey_url`` when ``HISTORY_VALKEY_URL`` is unset, since
        this service's own Valkey is the shared history bus by decision.
        """
        return self.history_valkey_url or self.valkey_url

    @cached_property
    def skill_roots(self) -> tuple[Path, ...]:
        roots = []
        for raw in self.skill_roots_raw.split(","):
            candidate = raw.strip()
            if candidate:
                roots.append(Path(candidate))
        if not roots:
            raise ValueError("at least one skill root is required")
        return tuple(roots)

    @cached_property
    def enabled_provider_ids(self) -> tuple[str, ...]:
        values = []
        for raw in self.enabled_provider_ids_raw.split(","):
            candidate = raw.strip()
            if candidate:
                values.append(candidate)
        if not values:
            raise ValueError("at least one enabled provider is required")
        unknown = sorted(set(values) - set(self.supported_provider_ids))
        if unknown:
            raise ValueError(f"unknown enabled providers: {', '.join(unknown)}")
        return tuple(values)

    @property
    def provider_prefixes(self) -> dict[str, str]:
        return {
            "nvidia": "nvidia",
            "openrouter": "openrouter",
            "mistral": "mistral",
            "claude": "anthropic",
            "openai": "openai",
            "lmstudio": "lmstudio",
            "gemini": "gemini",
            "opencodego": "opencodego",
        }
