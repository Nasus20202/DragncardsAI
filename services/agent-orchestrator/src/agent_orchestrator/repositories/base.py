from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from agent_orchestrator.storage.models import (
    AgentSession,
    Job,
    SessionEnabledMcp,
    SessionEnabledSkill,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RepositoryBase:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def _session_query(self) -> Select[tuple[AgentSession]]:
        return select(AgentSession).options(
            selectinload(AgentSession.model_config),
            selectinload(AgentSession.enabled_skills).selectinload(
                SessionEnabledSkill.skill
            ),
            selectinload(AgentSession.enabled_mcps).selectinload(SessionEnabledMcp.mcp),
            selectinload(AgentSession.player_configs),
            selectinload(AgentSession.jobs).selectinload(Job.events),
        )

    def _job_query(self) -> Select[tuple[Job]]:
        return select(Job).options(
            selectinload(Job.outputs),
            selectinload(Job.events),
            selectinload(Job.session).selectinload(AgentSession.model_config),
            selectinload(Job.session).selectinload(AgentSession.enabled_skills),
            selectinload(Job.session).selectinload(AgentSession.enabled_mcps),
            selectinload(Job.session).selectinload(AgentSession.player_configs),
        )
