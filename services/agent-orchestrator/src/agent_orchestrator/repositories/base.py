from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from agent_orchestrator.storage.models import AgentSession, Job, JobAttempt, PromptRun


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RepositoryBase:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    def _session_query(self) -> Select[tuple[AgentSession]]:
        return select(AgentSession).options(
            selectinload(AgentSession.model_config),
            selectinload(AgentSession.skill_assignments),
            selectinload(AgentSession.mcp_assignments),
            selectinload(AgentSession.jobs).selectinload(Job.events),
        )

    def _job_query(self) -> Select[tuple[Job]]:
        return select(Job).options(
            selectinload(Job.prompt_run),
            selectinload(Job.outputs),
            selectinload(Job.events),
            selectinload(Job.attempts_log),
            selectinload(Job.session).selectinload(AgentSession.model_config),
            selectinload(Job.session).selectinload(AgentSession.skill_assignments),
            selectinload(Job.session).selectinload(AgentSession.mcp_assignments),
        )

    async def _get_attempts_for_update(self, session: AsyncSession, job_id: str) -> list[JobAttempt]:
        result = await session.execute(select(JobAttempt).where(JobAttempt.job_id == job_id))
        return list(result.scalars())

    async def _get_prompt_run_for_update(self, session: AsyncSession, prompt_run_id: str) -> PromptRun:
        prompt_run = await session.get(PromptRun, prompt_run_id)
        assert prompt_run is not None
        return prompt_run
