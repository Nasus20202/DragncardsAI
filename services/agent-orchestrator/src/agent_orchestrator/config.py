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
)


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
    worker_max_tool_rounds: int = 64
    default_job_max_attempts: int = 2
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
    mcp_request_timeout_seconds: float = 30.0
    provider_models_cache_ttl_seconds: float = 600.0
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

    @field_validator("provider_models_cache_ttl_seconds")
    @classmethod
    def validate_provider_models_cache_ttl(cls, value: float) -> float:
        if value < 0:
            raise ValueError("provider_models_cache_ttl_seconds must be non-negative")
        return value

    @field_validator("supported_provider_ids")
    @classmethod
    def validate_providers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        missing = sorted(set(REQUIRED_PROVIDER_IDS) - set(value))
        if missing:
            raise ValueError(f"missing provider ids: {', '.join(missing)}")
        return value

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
        }
