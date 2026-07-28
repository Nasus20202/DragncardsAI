from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(
        self, value: datetime | None, dialect
    ) -> str | datetime | None:
        if value is None:
            return None
        normalized = (
            value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        )
        normalized = normalized.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return normalized.isoformat()
        return normalized

    def process_result_value(
        self, value: str | datetime | None, dialect
    ) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    multi_turn_memory: Mapped[bool] = mapped_column(Boolean, default=True)
    context_recent_message_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    context_recent_tool_exchange_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The persona a spawn falls back to when the agent names none. ``None`` keeps
    # the pre-persona behaviour: a child copies this session's own configuration.
    default_subagent_persona: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )
    terminated_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)

    model_config: Mapped[SessionModelConfig | None] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    enabled_skills: Mapped[list[SessionEnabledSkill]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    enabled_mcps: Mapped[list[SessionEnabledMcp]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    player_configs: Mapped[list[SessionPlayerConfig]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionPlayerConfig.player_id",
    )
    jobs: Mapped[list[Job]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionModelConfig(Base):
    __tablename__ = "session_model_configs"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    provider_id: Mapped[str] = mapped_column(String(64))
    model_name: Mapped[str] = mapped_column(String(255))
    gateway_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )

    session: Mapped[AgentSession] = relationship(back_populates="model_config")


class SkillRegistry(Base):
    __tablename__ = "skill_registries"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_path: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)


class SessionEnabledSkill(Base):
    __tablename__ = "session_enabled_skills"
    __table_args__ = (
        UniqueConstraint("session_id", "skill_name", name="uq_session_skill_enabled"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    skill_name: Mapped[str] = mapped_column(
        ForeignKey("skill_registries.name"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )

    session: Mapped[AgentSession] = relationship(back_populates="enabled_skills")
    skill: Mapped[SkillRegistry] = relationship()


class SessionPlayerConfig(Base):
    """Per-seat agent configuration for an orchestrated multi-player game.

    One row per player seat (``player1``..``playerN``) on the orchestrating
    session. Nullable columns mean *inherit from the orchestrator session*, so a
    user comparing two configurations only has to state the axis that differs.
    """

    __tablename__ = "session_player_configs"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # ``None`` inherits the orchestrator's enabled skills; a list (including the
    # empty list) overrides them.
    skills_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )

    session: Mapped[AgentSession] = relationship(back_populates="player_configs")


class AgentPersona(Base):
    """A reusable, user-authored agent configuration a subagent can be started from.

    A persona bundles the three things that make one agent behave differently
    from another: a detailed system prompt, a skill selection, and a tool
    configuration. It sits beside ``skill_registries`` and ``mcp_registries`` as a
    deployment-global table keyed by name — the service has no user identity to
    scope it to, and a persona exists precisely to outlive one session.

    Nullable columns carry meaning:

    * ``provider_id`` / ``model_name`` — inherit the spawning session's.
    * ``skills_json`` — ``None`` inherits the session's enabled skills; a list
      (including the empty list) replaces them.
    * ``allowed_tools_json`` — ``None`` means no narrowing; a list is an
      allowlist that can only REMOVE tools from what the child already exposes.

    A persona holds no credentials. It names a provider and a model; API keys
    live in the gateway configuration.
    """

    __tablename__ = "agent_personas"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    provider_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gateway_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    provider_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    skills_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    allowed_tools_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )


class McpRegistry(Base):
    __tablename__ = "mcp_registries"

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    transport: Mapped[str] = mapped_column(String(64))
    server_url: Mapped[str] = mapped_column(Text)
    headers_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    custom: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)


class SessionEnabledMcp(Base):
    __tablename__ = "session_enabled_mcps"
    __table_args__ = (
        UniqueConstraint("session_id", "mcp_name", name="uq_session_mcp_enabled"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    mcp_name: Mapped[str] = mapped_column(
        ForeignKey("mcp_registries.name"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )

    session: Mapped[AgentSession] = relationship(back_populates="enabled_mcps")
    mcp: Mapped[McpRegistry] = relationship()


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE")
    )
    prompt: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    job_type: Mapped[str] = mapped_column(String(32), default="prompt")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    parent_job_id: Mapped[str | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime(), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime(), default=utc_now, onupdate=utc_now
    )

    session: Mapped[AgentSession] = relationship(back_populates="jobs")
    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )
    outputs: Mapped[list[JobOutput]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)

    job: Mapped[Job] = relationship(back_populates="events")


class JobOutput(Base):
    __tablename__ = "job_outputs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    output_type: Mapped[str] = mapped_column(String(64), default="text")
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)

    job: Mapped[Job] = relationship(back_populates="outputs")


class CompactionRecord(Base):
    __tablename__ = "compaction_records"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), index=True
    )
    summary_text: Mapped[str] = mapped_column(Text)
    covers_up_to_job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE")
    )
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utc_now)

    session: Mapped[AgentSession] = relationship()
