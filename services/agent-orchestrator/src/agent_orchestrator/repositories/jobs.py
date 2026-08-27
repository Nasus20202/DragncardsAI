from __future__ import annotations

from typing import Any, NamedTuple

from sqlalchemy import func, select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import (
    AgentSession,
    Job,
    JobEvent,
    JobOutput,
)


class AppendedCancellation(NamedTuple):
    """A durable `cancellation` row this repository appended, and whose job it is on.

    Returned so the caller — which has the live event bus the repository does not —
    can publish the live copy of that row under the row's own id. The id matters:
    the SSE stream serves both the live bus and `list_events`, and the client
    collapses the two copies by id, so a live copy published without it renders the
    cancellation twice (DRA-34).

    A cancellation is a terminal event, so until it is *delivered* the client's
    stream stays open. That is why these ids are surfaced rather than left to the
    stream's own fallback poll to discover.
    """

    job_id: str
    event_id: int


class JobRepositoryMixin:
    async def enqueue_prompt_job(
        self,
        session_id: str,
        *,
        prompt: str,
        metadata_json: dict[str, Any] | None,
        max_attempts: int,
        parent_job_id: str | None = None,
    ) -> Job | None:
        async with self._session_factory() as session, session.begin():
            session_obj = await session.get(AgentSession, session_id)
            if session_obj is None:
                return None
            if session_obj.status != "active":
                raise ValueError("terminated")
            job = Job(
                session_id=session_id,
                prompt=prompt,
                metadata_json=metadata_json or {},
                max_attempts=max_attempts,
                parent_job_id=parent_job_id,
            )
            session.add(job)
            await session.flush()
            job_id = job.id
        await self.append_event(job_id, session_id, "progress", {"status": "queued"})
        loaded = await self.get_job(job_id)
        assert loaded is not None
        return loaded

    async def claim_next_job(self) -> Job | None:
        async with self._session_factory() as session, session.begin():
            stmt = (
                select(Job)
                .where(Job.status == "queued")
                .order_by(Job.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            job = result.scalars().first()
            if job is None:
                return None
            job.status = "running"
            job.started_at = utc_now()
            job.updated_at = utc_now()
            job.attempts += 1
            job_id = job.id
        loaded = await self.get_job(job_id)
        assert loaded is not None
        return loaded

    async def list_session_jobs(
        self,
        session_id: str,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        async with self._session_factory() as session:
            query = self._job_query().where(Job.session_id == session_id)
            count_query = (
                select(func.count())
                .select_from(Job)
                .where(Job.session_id == session_id)
            )
            if status is not None:
                query = query.where(Job.status == status)
                count_query = count_query.where(Job.status == status)
            total = await session.scalar(count_query)
            result = await session.execute(
                query.order_by(Job.created_at.desc()).offset(offset).limit(limit)
            )
            return list(result.scalars().unique()), int(total or 0)

    async def set_parent_job_id(self, job_id: str, parent_job_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is not None:
                job.parent_job_id = parent_job_id
                job.updated_at = utc_now()

    async def get_job(self, job_id: str) -> Job | None:
        async with self._session_factory() as session:
            result = await session.execute(self._job_query().where(Job.id == job_id))
            return result.scalars().unique().first()

    async def request_cancel(
        self, job_id: str
    ) -> tuple[Job | None, list[AppendedCancellation]]:
        """Request cancellation of a job and its active children.

        Returns the job and every durable `cancellation` row this appended — one
        for the job, one per active child. The caller is expected to publish a
        live copy of each under the returned id, because a `cancellation` is
        terminal and an undelivered one leaves that job's SSE stream open.
        """
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None, []
            now = utc_now()
            job.cancellation_requested_at = now
            if job.status == "queued":
                job.status = "cancelled"
                job.completed_at = now
            job.updated_at = now
            session_id = job.session_id

            # Propagate cancellation to all active child jobs.
            child_result = await session.execute(
                select(Job.id, Job.session_id, Job.status).where(
                    Job.parent_job_id == job_id,
                    Job.status.in_(["queued", "running"]),
                )
            )
            child_rows = child_result.all()

            if child_rows:
                child_ids = [r.id for r in child_rows]
                queued_child_ids = [r.id for r in child_rows if r.status == "queued"]
                await session.execute(
                    update(Job)
                    .where(Job.id.in_(child_ids))
                    .values(cancellation_requested_at=now, updated_at=now)
                )
                if queued_child_ids:
                    await session.execute(
                        update(Job)
                        .where(Job.id.in_(queued_child_ids))
                        .values(status="cancelled", completed_at=now)
                    )

        appended = [
            AppendedCancellation(
                job_id,
                await self.append_event(
                    job_id, session_id, "cancellation", {"requested": True}
                ),
            )
        ]
        for row in child_rows:
            appended.append(
                AppendedCancellation(
                    row.id,
                    await self.append_event(
                        row.id, row.session_id, "cancellation", {"requested": True}
                    ),
                )
            )

        return await self.get_job(job_id), appended

    async def append_event(
        self,
        job_id: str,
        session_id: str,
        event_type: str,
        payload_json: dict[str, Any],
    ) -> int:
        async with self._session_factory() as session, session.begin():
            item = JobEvent(
                job_id=job_id,
                session_id=session_id,
                event_type=event_type,
                payload_json=payload_json,
            )
            session.add(item)
            await session.flush()
            return item.id

    async def update_event(self, event_id: int, payload_json: dict[str, Any]) -> None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(JobEvent, event_id)
            if item is not None:
                item.payload_json = payload_json

    async def list_events(
        self, job_id: str, *, after_id: int = 0, limit: int = 100
    ) -> list[JobEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobEvent)
                .where(JobEvent.job_id == job_id, JobEvent.id > after_id)
                .order_by(JobEvent.id.asc())
                .limit(limit)
            )
            return list(result.scalars())

    async def store_output(self, job_id: str, content: str) -> None:
        async with self._session_factory() as session, session.begin():
            session.add(JobOutput(job_id=job_id, content=content))

    async def mark_job_completed(self, job_id: str, result_text: str) -> Job | None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            now = utc_now()
            job.status = "completed"
            job.result_text = result_text
            job.completed_at = now
            job.updated_at = now
        await self.store_output(job_id, result_text)
        return await self.get_job(job_id)

    async def mark_job_failed(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> Job | None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            now = utc_now()
            should_retry = (
                retryable
                and job.attempts < job.max_attempts
                and job.cancellation_requested_at is None
            )
            job.error_code = error_code
            job.error_message = error_message
            job.updated_at = now
            if should_retry:
                job.status = "queued"
                job.started_at = None
            else:
                job.status = "failed"
                job.completed_at = now
        return await self.get_job(job_id)

    async def mark_job_interrupted(
        self,
        job_id: str,
        *,
        result_text: str,
    ) -> Job | None:
        """Mark a job as interrupted (tool round limit hit).

        Interrupted jobs are terminal but distinct from failures — they contain
        valid partial work that should be replayed into the next job's context.
        """
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            now = utc_now()
            job.status = "interrupted"
            job.error_code = "tool_round_limit"
            job.error_message = "Tool round limit reached"
            job.result_text = result_text
            job.completed_at = now
            job.updated_at = now
        return await self.get_job(job_id)

    async def mark_job_cancelled(self, job_id: str, *, reason: str) -> int | None:
        """Mark a job cancelled, returning the id of the `cancellation` row appended.

        The id is returned, rather than the job, because the only thing the two
        callers need from this is something to publish the live copy under. A
        `cancellation` is terminal, so leaving it to the stream's fallback poll to
        discover holds that client's stream open for the whole interval. `None`
        means the job was gone and nothing was appended.
        """
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            now = utc_now()
            job.status = "cancelled"
            job.error_code = "cancelled"
            job.error_message = reason
            job.completed_at = now
            job.updated_at = now
            session_id = job.session_id
        return await self.append_event(
            job_id, session_id, "cancellation", {"reason": reason}
        )

    async def get_job_cancellation_requested(self, job_id: str) -> bool:
        async with self._session_factory() as session:
            job = await session.get(Job, job_id)
            return bool(job and job.cancellation_requested_at)
