from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import AgentSession, Job, JobAttempt, JobEvent, JobOutput, PromptRun


class JobRepositoryMixin:
    async def enqueue_prompt_job(
        self,
        session_id: str,
        *,
        prompt: str,
        metadata_json: dict[str, Any] | None,
        max_attempts: int,
    ) -> Job | None:
        async with self._session_factory() as session, session.begin():
            session_obj = await session.get(AgentSession, session_id)
            if session_obj is None:
                return None
            if session_obj.status != "active":
                raise ValueError("terminated")
            prompt_run = PromptRun(
                session_id=session_id,
                prompt=prompt,
                metadata_json=metadata_json or {},
            )
            session.add(prompt_run)
            await session.flush()
            job = Job(
                session_id=session_id,
                prompt_run_id=prompt_run.id,
                max_attempts=max_attempts,
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
            prompt_run = await self._get_prompt_run_for_update(session, job.prompt_run_id)
            prompt_run.status = "running"
            prompt_run.updated_at = utc_now()
            session.add(JobAttempt(job_id=job.id, attempt_number=job.attempts, status="running"))
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
            count_query = select(func.count()).select_from(Job).where(Job.session_id == session_id)
            if status is not None:
                query = query.where(Job.status == status)
                count_query = count_query.where(Job.status == status)
            total = await session.scalar(count_query)
            result = await session.execute(
                query.order_by(Job.created_at.desc()).offset(offset).limit(limit)
            )
            return list(result.scalars().unique()), int(total or 0)

    async def get_job(self, job_id: str) -> Job | None:
        async with self._session_factory() as session:
            result = await session.execute(self._job_query().where(Job.id == job_id))
            return result.scalars().unique().first()

    async def request_cancel(self, job_id: str) -> Job | None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            now = utc_now()
            job.cancellation_requested_at = now
            if job.status == "queued":
                job.status = "cancelled"
                job.completed_at = now
                prompt_run = await self._get_prompt_run_for_update(session, job.prompt_run_id)
                prompt_run.status = "cancelled"
                prompt_run.updated_at = now
            job.updated_at = now
            session_id = job.session_id
        await self.append_event(job_id, session_id, "cancellation", {"requested": True})
        return await self.get_job(job_id)

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

    async def list_events(self, job_id: str, *, after_id: int = 0, limit: int = 100) -> list[JobEvent]:
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
            prompt_run = await self._get_prompt_run_for_update(session, job.prompt_run_id)
            prompt_run.status = "completed"
            prompt_run.updated_at = now
            attempts = await self._get_attempts_for_update(session, job_id)
            for attempt in attempts:
                if attempt.status == "running" and attempt.completed_at is None:
                    attempt.status = "completed"
                    attempt.completed_at = now
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
            prompt_run = await self._get_prompt_run_for_update(session, job.prompt_run_id)
            now = utc_now()
            should_retry = retryable and job.attempts < job.max_attempts and job.cancellation_requested_at is None
            job.error_code = error_code
            job.error_message = error_message
            job.updated_at = now
            attempts = await self._get_attempts_for_update(session, job_id)
            for attempt in attempts:
                if attempt.status == "running" and attempt.completed_at is None:
                    attempt.status = "failed"
                    attempt.error_message = error_message
                    attempt.completed_at = now
            if should_retry:
                job.status = "queued"
                prompt_run.status = "queued"
                job.started_at = None
            else:
                job.status = "failed"
                job.completed_at = now
                prompt_run.status = "failed"
            prompt_run.updated_at = now
        return await self.get_job(job_id)

    async def mark_job_cancelled(self, job_id: str, *, reason: str) -> Job | None:
        async with self._session_factory() as session, session.begin():
            job = await session.get(Job, job_id)
            if job is None:
                return None
            prompt_run = await self._get_prompt_run_for_update(session, job.prompt_run_id)
            now = utc_now()
            job.status = "cancelled"
            job.error_code = "cancelled"
            job.error_message = reason
            job.completed_at = now
            job.updated_at = now
            prompt_run.status = "cancelled"
            prompt_run.updated_at = now
            attempts = await self._get_attempts_for_update(session, job_id)
            for attempt in attempts:
                if attempt.status == "running" and attempt.completed_at is None:
                    attempt.status = "cancelled"
                    attempt.error_message = reason
                    attempt.completed_at = now
            session_id = job.session_id
        await self.append_event(job_id, session_id, "cancellation", {"reason": reason})
        return await self.get_job(job_id)

    async def get_job_cancellation_requested(self, job_id: str) -> bool:
        async with self._session_factory() as session:
            job = await session.get(Job, job_id)
            return bool(job and job.cancellation_requested_at)
