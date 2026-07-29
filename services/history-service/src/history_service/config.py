from __future__ import annotations

import os
import socket

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """History-service configuration.

    Secrets (database credentials) only ever live in ``history_database_url`` and
    are never echoed by the health/readiness endpoints.
    """

    model_config = SettingsConfigDict(extra="ignore")

    history_database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5442/history_service",
        validation_alias=AliasChoices("history_database_url", "HISTORY_DATABASE_URL"),
    )
    valkey_url: str = Field(
        default="redis://localhost:6381/0",
        validation_alias=AliasChoices("valkey_url", "VALKEY_URL"),
    )
    http_host: str = "0.0.0.0"
    http_port: int = 4004

    # CORS allowlist (comma-separated). The dashboard reaches history-service via
    # a server-side proxy (not browser-direct), so a strict allowlist does NOT
    # break normal dashboard use; the default covers the local dashboard origin.
    # This must never widen back to "*": Compose publishes 4004 on the host, so a
    # wildcard lets ANY page a developer visits drive DELETE /games/{game_id} and
    # POST /games/{game_id}/events from the browser, destroying or forging the one
    # durable record of what an agent did — the same operations deliberately
    # withheld from the MCP surface (see ``mcp_server.EXCLUDED_ROUTES``).
    history_cors_allow_origins: str = Field(
        default="http://localhost:3001,http://127.0.0.1:3001",
        validation_alias=AliasChoices(
            "history_cors_allow_origins", "HISTORY_CORS_ALLOW_ORIGINS"
        ),
    )

    # Shared ingestion stream contract (must match producers).
    history_ingest_stream: str = Field(
        default="history:ingest",
        validation_alias=AliasChoices("history_ingest_stream", "HISTORY_INGEST_STREAM"),
    )
    history_ingest_consumer_group: str = Field(
        default="history-service",
        validation_alias=AliasChoices(
            "history_ingest_consumer_group", "HISTORY_INGEST_CONSUMER_GROUP"
        ),
    )
    history_ingest_consumer_name: str = Field(
        default="",
        validation_alias=AliasChoices(
            "history_ingest_consumer_name", "HISTORY_INGEST_CONSUMER_NAME"
        ),
    )
    history_ingest_stream_maxlen: int = Field(
        default=100_000,
        validation_alias=AliasChoices(
            "history_ingest_stream_maxlen", "HISTORY_INGEST_STREAM_MAXLEN"
        ),
    )
    history_consumer_lag_alert_threshold: int = Field(
        default=1_000,
        validation_alias=AliasChoices(
            "history_consumer_lag_alert_threshold",
            "HISTORY_CONSUMER_LAG_ALERT_THRESHOLD",
        ),
    )

    # Snapshot cadence.
    snapshot_every_n_events: int = Field(
        default=25,
        validation_alias=AliasChoices(
            "snapshot_every_n_events", "SNAPSHOT_EVERY_N_EVENTS"
        ),
    )
    snapshot_max_interval_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices(
            "snapshot_max_interval_seconds", "SNAPSHOT_MAX_INTERVAL_SECONDS"
        ),
    )

    # Ceiling on an uploaded history bundle. Deliberately far above the
    # agent-orchestrator's MAX_REQUEST_BODY_BYTES (8 MiB): a lossless bundle
    # carries a full board state per game-service event, so a real game runs to
    # tens of megabytes. The import reader enforces this while streaming and
    # answers 413 with the same body the orchestrator's cap uses.
    history_import_max_bytes: int = Field(
        default=64 * 1024 * 1024,
        validation_alias=AliasChoices(
            "history_import_max_bytes", "HISTORY_IMPORT_MAX_BYTES"
        ),
    )

    # Producer base URLs (used by snapshotting + restore orchestration).
    game_service_base_url: str = Field(
        default="http://localhost:4001",
        validation_alias=AliasChoices("game_service_base_url", "GAME_SERVICE_BASE_URL"),
    )
    agent_orchestrator_base_url: str = Field(
        default="http://localhost:4002",
        validation_alias=AliasChoices(
            "agent_orchestrator_base_url", "AGENT_ORCHESTRATOR_BASE_URL"
        ),
    )

    ingester_poll_block_ms: int = 2_000
    ingester_batch_size: int = 64

    # Minimum idle time before a pending stream entry (from a crashed replica or
    # a transient commit failure) is reclaimed via XAUTOCLAIM and re-processed.
    history_ingest_claim_min_idle_ms: int = Field(
        default=30_000,
        validation_alias=AliasChoices(
            "history_ingest_claim_min_idle_ms", "HISTORY_INGEST_CLAIM_MIN_IDLE_MS"
        ),
    )

    @field_validator("history_ingest_stream_maxlen")
    @classmethod
    def validate_maxlen(cls, value: int) -> int:
        if value < 1:
            raise ValueError("history_ingest_stream_maxlen must be at least 1")
        return value

    @field_validator("history_consumer_lag_alert_threshold")
    @classmethod
    def validate_lag_threshold(cls, value: int) -> int:
        if value < 0:
            raise ValueError(
                "history_consumer_lag_alert_threshold must be non-negative"
            )
        return value

    @field_validator("history_ingest_claim_min_idle_ms")
    @classmethod
    def validate_claim_min_idle(cls, value: int) -> int:
        if value < 0:
            raise ValueError("history_ingest_claim_min_idle_ms must be non-negative")
        return value

    @field_validator("history_import_max_bytes")
    @classmethod
    def validate_import_max_bytes(cls, value: int) -> int:
        if value < 1:
            raise ValueError("history_import_max_bytes must be at least 1")
        return value

    @field_validator("snapshot_every_n_events")
    @classmethod
    def validate_snapshot_count(cls, value: int) -> int:
        if value < 1:
            raise ValueError("snapshot_every_n_events must be at least 1")
        return value

    @field_validator("snapshot_max_interval_seconds")
    @classmethod
    def validate_snapshot_interval(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("snapshot_max_interval_seconds must be positive")
        return value

    @field_validator("http_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("http_port must be a valid TCP port")
        return value

    @property
    def cors_allow_origins(self) -> list[str]:
        """Configured CORS origins as a list (comma-separated, trimmed)."""
        return [
            o.strip() for o in self.history_cors_allow_origins.split(",") if o.strip()
        ]

    @property
    def consumer_name(self) -> str:
        """A stable consumer name for this process within the consumer group.

        Falls back to ``<hostname>:<pid>`` so concurrent replicas claim distinct
        pending entry lists while sharing the single consumer group.
        """
        if self.history_ingest_consumer_name:
            return self.history_ingest_consumer_name
        return f"{socket.gethostname()}:{os.getpid()}"
