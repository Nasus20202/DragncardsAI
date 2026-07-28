from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import JobQuestion

QUESTION_STATUS_PENDING = "pending"
QUESTION_STATUS_ANSWERED = "answered"
QUESTION_STATUS_CLOSED = "closed"


class QuestionRepositoryMixin:
    """Persistence for questions the agent asked the user.

    Every transition out of ``pending`` is an ``UPDATE ... WHERE status =
    'pending'``, and the row count it reports is the decision: one means this
    caller won the transition, zero means somebody already took it. That is what
    makes a double answer a database fact rather than a race between two HTTP
    requests that may be handled by two replicas.
    """

    async def create_job_question(
        self,
        job_id: str,
        session_id: str,
        *,
        question: str,
        choices: list[dict[str, Any]],
        allow_free_text: bool,
    ) -> JobQuestion:
        async with self._session_factory() as session, session.begin():
            item = JobQuestion(
                job_id=job_id,
                session_id=session_id,
                question=question,
                choices_json=list(choices),
                allow_free_text=allow_free_text,
                status=QUESTION_STATUS_PENDING,
            )
            session.add(item)
            await session.flush()
            question_id = item.id
        loaded = await self.get_job_question(question_id)
        assert loaded is not None
        return loaded

    async def get_job_question(self, question_id: str) -> JobQuestion | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(JobQuestion).where(JobQuestion.id == question_id)
            )
            return result.scalars().first()

    async def answer_job_question(
        self,
        question_id: str,
        *,
        source: str,
        value: str | None,
        label: str | None,
        text: str | None,
    ) -> JobQuestion | None:
        """Record an answer, or return None when the question was not pending.

        None means "somebody already resolved this", which the caller reports as
        a conflict. It deliberately does not distinguish "already answered" from
        "already closed": both mean this answer is too late.
        """
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(JobQuestion)
                .where(
                    JobQuestion.id == question_id,
                    JobQuestion.status == QUESTION_STATUS_PENDING,
                )
                .values(
                    status=QUESTION_STATUS_ANSWERED,
                    answer_source=source,
                    answer_value=value,
                    answer_label=label,
                    answer_text=text,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                return None
        return await self.get_job_question(question_id)

    async def close_job_question(
        self, question_id: str, *, reason: str
    ) -> JobQuestion | None:
        """Stop a question awaiting an answer, or return None if it already was.

        Called before a waiting run gives up, so that an answer arriving
        afterwards is refused rather than recorded against a question nobody is
        reading any more.
        """
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(JobQuestion)
                .where(
                    JobQuestion.id == question_id,
                    JobQuestion.status == QUESTION_STATUS_PENDING,
                )
                .values(
                    status=QUESTION_STATUS_CLOSED,
                    closed_reason=reason,
                    updated_at=utc_now(),
                )
            )
            if result.rowcount == 0:
                return None
        return await self.get_job_question(question_id)
