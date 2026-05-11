"""Repository methods for context management (compaction records, replay queries)."""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import (
    AgentSession,
    CompactionRecord,
    Job,
    JobEvent,
    PromptRun,
)

logger = logging.getLogger(__name__)

COMPACTION_SYSTEM_PROMPT = """\
You are summarizing a Marvel Champions card game session history for context compression.

Produce a concise but complete summary that MUST preserve:
- Hero identity, current HP, and max HP
- Villain name, current HP, max HP, and stage
- Current threat level on each scheme
- All cards currently in play (hero side and villain side)
- Encounter deck status (number of cards, any face-up cards)
- What the agent did in the most recent turn and the outcome
- Any notable game state flags (e.g., confused, stunned, toughness tokens)

Do NOT include:
- Step-by-step reasoning about past decisions
- Verbose tool call details
- Intermediate game states that have since changed

Output plain text. Be concise but complete. A future AI agent will use this summary as its only memory of prior turns.
"""


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
            prompt_run = PromptRun(
                session_id=session_id,
                prompt="[COMPACTION]",
                metadata_json={"compaction": True},
            )
            session.add(prompt_run)
            await session.flush()

            job = Job(
                session_id=session_id,
                prompt_run_id=prompt_run.id,
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
    ) -> list[Job]:
        """Return completed jobs for this session in chronological order.

        Excludes current_job_id.  If after_job_id is set, only returns jobs
        created strictly after that job (compaction checkpoint).
        """
        async with self._session_factory() as session:
            query = (
                select(Job)
                .options(
                    selectinload(Job.prompt_run),
                    selectinload(Job.events),
                )
                .where(
                    Job.session_id == session_id,
                    Job.id != current_job_id,
                    Job.status == "completed",
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
        """Sum tokens_used across completed jobs since the last compaction checkpoint."""
        async with self._session_factory() as session:
            query = select(func.sum(Job.tokens_used)).where(
                Job.session_id == session_id,
                Job.status == "completed",
                Job.job_type != "compaction",
            )
            if after_job_id:
                checkpoint = await session.get(Job, after_job_id)
                if checkpoint is not None:
                    query = query.where(Job.created_at > checkpoint.created_at)
            total = await session.scalar(query)
            return int(total or 0)

    async def get_latest_completed_job_id(self, session_id: str) -> str | None:
        """Return the id of the most recently completed job for this session."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(Job.id)
                .where(Job.session_id == session_id, Job.status == "completed")
                .order_by(Job.completed_at.desc())
                .limit(1)
            )
            return result.scalar()

    async def get_context_metadata(
        self, session_id: str, context_window_size: int
    ) -> dict:
        """Return context health metadata for a session."""
        compaction = await self.get_latest_compaction_record(session_id)
        after_job_id = compaction.covers_up_to_job_id if compaction else None
        tokens_used = await self.get_tokens_used_since_compaction(
            session_id, after_job_id=after_job_id
        )
        # Include the compaction summary itself in the token count — the summary
        # message is injected at the top of every subsequent context window.
        if compaction:
            tokens_used += compaction.tokens_used
        compaction_count = await self.count_compaction_records(session_id)
        usage_ratio = (
            tokens_used / context_window_size if context_window_size > 0 else 0.0
        )

        async with self._session_factory() as db_session:
            session_obj = await db_session.get(AgentSession, session_id)
        multi_turn_memory = session_obj.multi_turn_memory if session_obj else True

        return {
            "tokens_used": tokens_used,
            "context_window_size": context_window_size,
            "usage_ratio": round(min(usage_ratio, 1.0), 6),
            "compaction_count": compaction_count,
            "last_compacted_at": compaction.created_at if compaction else None,
            "multi_turn_memory": multi_turn_memory,
        }
