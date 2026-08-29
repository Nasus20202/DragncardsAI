"""Repository methods for context management (compaction records, replay queries)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.models import (
    AgentSession,
    CompactionRecord,
    Job,
    JobEvent,
)


class ContextRepositoryMixin:
    # ------------------------------------------------------------------
    # CompactionRecord CRUD
    # ------------------------------------------------------------------

    async def get_latest_compaction_record(
        self, session_id: str
    ) -> CompactionRecord | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CompactionRecord)
                .where(CompactionRecord.session_id == session_id)
                .order_by(CompactionRecord.created_at.desc())
                .limit(1)
            )
            return result.scalars().first()

    async def list_compaction_records(self, session_id: str) -> list[CompactionRecord]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(CompactionRecord)
                .where(CompactionRecord.session_id == session_id)
                .order_by(CompactionRecord.created_at.asc())
            )
            return list(result.scalars())

    async def create_compaction_record(
        self,
        session_id: str,
        *,
        summary_text: str,
        covers_up_to_job_id: str,
        tokens_used: int,
    ) -> CompactionRecord:
        async with self._session_factory() as session, session.begin():
            record = CompactionRecord(
                session_id=session_id,
                summary_text=summary_text,
                covers_up_to_job_id=covers_up_to_job_id,
                tokens_used=tokens_used,
            )
            session.add(record)
            await session.flush()
            record_id = record.id
        async with self._session_factory() as session:
            result = await session.get(CompactionRecord, record_id)
            assert result is not None
            return result

    async def create_compaction_job(
        self,
        session_id: str,
        *,
        summary_text: str,
        tokens_used: int,
    ) -> str:
        """Create a synthetic completed job that records the compaction summary as a model_output event.

        This makes compaction visible in the session transcript. The job has
        job_type='compaction' so it is excluded from message-history replay and
        token-usage accounting (the CompactionRecord tracks those instead).

        Returns the new job id.
        """
        now = utc_now()
        async with self._session_factory() as session, session.begin():
            job = Job(
                session_id=session_id,
                prompt="[COMPACTION]",
                metadata_json={"compaction": True},
                job_type="compaction",
                status="completed",
                attempts=1,
                tokens_used=tokens_used,
                started_at=now,
                completed_at=now,
                result_text=summary_text,
            )
            session.add(job)
            await session.flush()
            job_id = job.id

            event = JobEvent(
                job_id=job_id,
                session_id=session_id,
                event_type="model_output",
                payload_json={"text": summary_text, "compaction": True},
            )
            session.add(event)

        return job_id

    async def count_compaction_records(self, session_id: str) -> int:
        async with self._session_factory() as session:
            total = await session.scalar(
                select(func.count())
                .select_from(CompactionRecord)
                .where(CompactionRecord.session_id == session_id)
            )
            return int(total or 0)

    # ------------------------------------------------------------------
    # Replay queries
    # ------------------------------------------------------------------

    async def list_completed_jobs_for_replay(
        self,
        session_id: str,
        *,
        current_job_id: str,
        after_job_id: str | None,
        include_running: bool = False,
    ) -> list[Job]:
        """Return jobs for this session in chronological order for context replay.

        Includes completed, interrupted, and failed jobs (and optionally running jobs
        when estimating in-flight session context) so that partial work is visible.
        Excludes current_job_id.  If after_job_id is set, only returns jobs
        created strictly after that job (compaction checkpoint).
        """
        statuses = (
            ["completed", "interrupted", "failed", "running"]
            if include_running
            else ["completed", "interrupted", "failed"]
        )
        async with self._session_factory() as session:
            query = (
                select(Job)
                .options(
                    selectinload(Job.events),
                )
                .where(
                    Job.session_id == session_id,
                    Job.id != current_job_id,
                    Job.status.in_(statuses),
                    Job.job_type != "compaction",
                )
            )
            if after_job_id:
                # Fetch created_at of the checkpoint job to filter by time
                checkpoint = await session.get(Job, after_job_id)
                if checkpoint is not None:
                    query = query.where(Job.created_at > checkpoint.created_at)

            result = await session.execute(query.order_by(Job.created_at.asc()))
            return list(result.scalars().unique())

    # ------------------------------------------------------------------
    # Token usage
    # ------------------------------------------------------------------

    async def update_job_tokens_used(self, job_id: str, tokens_used: int) -> None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is not None:
                job.tokens_used = tokens_used
                job.updated_at = utc_now()

    async def get_tokens_used_since_compaction(
        self, session_id: str, *, after_job_id: str | None
    ) -> int:
        """Sum tokens_used across completed and interrupted jobs since the last compaction checkpoint."""
        async with self._session_factory() as session:
            query = select(func.sum(Job.tokens_used)).where(
                Job.session_id == session_id,
                Job.status.in_(["completed", "interrupted"]),
                Job.job_type != "compaction",
            )
            if after_job_id:
                checkpoint = await session.get(Job, after_job_id)
                if checkpoint is not None:
                    query = query.where(Job.created_at > checkpoint.created_at)
            total = await session.scalar(query)
            return int(total or 0)

    async def get_latest_completed_job_id(self, session_id: str) -> str | None:
        """Return the id of the most recently completed or interrupted job for this session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Job.id)
                .where(
                    Job.session_id == session_id,
                    Job.status.in_(["completed", "interrupted"]),
                    Job.job_type != "compaction",
                )
                .order_by(Job.completed_at.desc())
                .limit(1)
            )
            return result.scalar()

    async def get_session_context_snapshot(
        self, session_id: str
    ) -> AgentSession | None:
        async with self._session_factory() as session:
            result = await session.execute(
                self._session_query().where(AgentSession.id == session_id)
            )
            return result.scalars().unique().first()

    async def get_context_metadata(
        self,
        session_id: str,
        context_window_size: int,
        *,
        skill_registry: SkillRegistry,
        request_tools: list[dict[str, Any]],
    ) -> dict:
        """Return context health metadata for a session.

        `request_tools` is the OpenAI-shaped tool list a top-level job on this
        session would send — built-in and MCP alike. The caller resolves it,
        because building the built-in half needs the live event bus and that is
        an API-layer dependency.
        """
        metadata = await SessionTranscriptService(self).build_context_metadata(
            session_id,
            context_window_size,
            skill_registry=skill_registry,
            request_tools=request_tools,
        )
        return metadata.as_dict()
