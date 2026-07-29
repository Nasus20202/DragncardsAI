from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.history_emitter import HistoryEventEmitter
from agent_orchestrator.runtime.live_event_resilience import (
    best_effort_live_event_bus,
)
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.models import Job
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class WorkerService:
    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        bifrost_client: BifrostClient,
        live_event_bus: LiveEventBus,
        mcp_tool_catalog: McpToolCatalog,
        skill_registry: SkillRegistry,
        history_emitter: HistoryEventEmitter | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._bifrost_client = bifrost_client
        # Wrapped here as well as in `create_app`, and the wrap is idempotent.
        # The guarantee that a Valkey blip cannot fail a job has to hold for the
        # job runtime however it was assembled, not only for the one path that
        # goes through the app factory (DRA-42).
        self._live_event_bus = best_effort_live_event_bus(live_event_bus)
        self._mcp_tool_catalog = mcp_tool_catalog
        self._skill_registry = skill_registry
        self._history_emitter = history_emitter
        self._stop_event = asyncio.Event()
        self.is_running = False
        self._child_tasks: set[asyncio.Task[None]] = set()
        self._transcript_service = SessionTranscriptService(repository)
        self._prompt_run_service = PromptRunService(
            dependencies=PromptRunDependencies(
                settings=settings,
                repository=repository,
                bifrost_client=bifrost_client,
                live_event_bus=self._live_event_bus,
                mcp_tool_catalog=mcp_tool_catalog,
                skill_registry=skill_registry,
                history_emitter=history_emitter,
            ),
            transcript_service=self._transcript_service,
            schedule_child_job=self.run_child_job,
        )

    async def run_forever(self) -> None:
        self.is_running = True
        logger.info("Worker loop started")
        try:
            while not self._stop_event.is_set():
                job = None
                try:
                    with tracer.start_as_current_span(
                        "agent_orchestrator.claim_next_job"
                    ):
                        job = await self._repository.claim_next_job()
                    if job is None:
                        await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                        continue
                    logger.info("Claimed job %s", job.id)
                    task = asyncio.create_task(self._run_job(job), name=f"job-{job.id}")
                    self._child_tasks.add(task)
                    task.add_done_callback(self._child_tasks.discard)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if job is None:
                        logger.exception(
                            "Worker loop iteration failed before claiming a job"
                        )
                    else:
                        logger.exception(
                            "Worker loop iteration failed for job %s", job.id
                        )
                    if not self._stop_event.is_set():
                        await asyncio.sleep(self._settings.worker_poll_interval_seconds)
        finally:
            self.is_running = False
            logger.info("Worker loop stopped")

    async def run_child_job(self, job_id: str) -> None:
        """Claim and run a specific child job by ID, used by spawn_subagent to run the child concurrently."""
        task = asyncio.create_task(
            self._run_child_job(job_id), name=f"child-job-{job_id}"
        )
        self._child_tasks.add(task)
        task.add_done_callback(self._child_tasks.discard)

    async def _run_child_job(self, job_id: str) -> None:
        """Internal: claim and execute the child job."""
        job = await self._repository.get_job(job_id)
        if job is None or job.status != "queued":
            return
        # Claim the job manually
        claimed = None
        for _ in range(20):
            claimed = await self._repository.claim_next_job()
            if claimed is not None and claimed.id == job_id:
                break
            if claimed is not None:
                # Put it back by treating it as a job we don't run
                # This should not happen in normal usage; just log
                logger.warning(
                    "run_child_job claimed unexpected job %s while waiting for %s",
                    claimed.id,
                    job_id,
                )
                break
            await asyncio.sleep(0.01)
        if claimed is not None and claimed.id == job_id:
            await self._run_job(claimed)

    async def stop(self) -> None:
        self._stop_event.set()
        logger.info("Worker stop requested")
        if self._child_tasks:
            logger.info("Waiting for %d child job(s) to finish", len(self._child_tasks))
            for task in list(self._child_tasks):
                task.cancel()
            await asyncio.gather(*self._child_tasks, return_exceptions=True)
            logger.info("All child jobs finished")

    async def _record_failure(self, job: Job, failure: dict[str, Any]) -> None:
        await self._prompt_run_service.record_failure(job, failure)

    async def _append_tool_call_event(
        self,
        *,
        job_id: str,
        session_id: str,
        tool_call_id: str,
        exposed_tool_name: str,
        tool_name: str,
        assignment: str | None,
        server_url: str | None,
        arguments: dict[str, Any],
    ) -> None:
        await self._prompt_run_service.append_tool_call_event(
            job_id=job_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            exposed_tool_name=exposed_tool_name,
            tool_name=tool_name,
            assignment=assignment,
            server_url=server_url,
            arguments=arguments,
        )

    async def _append_tool_result_event(
        self,
        *,
        job_id: str,
        session_id: str,
        tool_call_id: str,
        exposed_tool_name: str,
        tool_name: str,
        assignment: str | None,
        server_url: str | None,
        result: dict[str, Any],
    ) -> None:
        await self._prompt_run_service.append_tool_result_event(
            job_id=job_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            exposed_tool_name=exposed_tool_name,
            tool_name=tool_name,
            assignment=assignment,
            server_url=server_url,
            result=result,
        )

    async def _complete_job(
        self, job: Job, content: str, accumulated_job_tokens: int
    ) -> None:
        await self._prompt_run_service.complete_job(
            job, content, accumulated_job_tokens
        )

    async def _maybe_terminate_child_session(self, job: Job) -> None:
        """Terminate the session if this is a child (subagent) job."""
        await self._prompt_run_service._maybe_terminate_child_session(job)

    async def _run_job(self, job: Job) -> None:
        try:
            await self._prompt_run_service.run(job)
        except Exception:
            # `_run_job` runs as a detached task, so an escaping exception would
            # silently leave the job in `running`. Non-terminal jobs are skipped
            # by context replay, which would drop the prompt from the session
            # transcript, so force the job to a terminal status as a last resort.
            logger.exception(
                "Job %s crashed outside prompt-run failure handling", job.id
            )
            await self._force_terminal_failure(job)

    async def _force_terminal_failure(self, job: Job) -> None:
        """Record and announce a failure for a job that crashed out of its own
        failure handling.

        Announcing matters as much as persisting. A parent blocked in
        `wait_for_subagent`, the child monitor, and the dashboard's event stream
        all learn a job's fate from the live bus, so a database-only failure
        leaves them waiting on an event that never arrives. Each step is
        independently guarded: this is the last line of defence and a second
        exception here must not undo the work that already succeeded.
        """
        code = "worker_crash"
        message = "Job crashed before reaching a terminal status"
        failure: dict[str, Any] = {
            "code": code,
            "message": message,
            "retryable": False,
        }
        try:
            await self._repository.mark_job_failed(
                job.id,
                error_code=code,
                error_message=message,
                retryable=False,
            )
        except Exception:
            logger.exception("Failed to mark crashed job %s as failed", job.id)
        durable_event_id: int | None = None
        try:
            durable_event_id = await self._repository.append_event(
                job.id, job.session_id, "failure", failure
            )
        except Exception:
            logger.exception("Failed to record the crash of job %s", job.id)
        try:
            await self._live_event_bus.publish(
                job.id, "failure", failure, durable_event_id=durable_event_id
            )
        except Exception:
            logger.exception("Failed to announce the crash of job %s", job.id)
        await self._maybe_terminate_child_session(job)

    async def _maybe_auto_compact(self, job_id: str, session_id: str) -> None:
        """Auto-compact context if estimated usage ratio exceeds threshold."""
        await self._prompt_run_service.maybe_auto_compact(job_id, session_id)

    def _format_execution_error(self, exc: Exception) -> str:
        return self._prompt_run_service.format_execution_error(exc)

    def _classify_execution_failure(self, exc: Exception) -> dict[str, Any]:
        return self._prompt_run_service.classify_execution_failure(exc)

    async def _append_invalid_tool_result(
        self,
        *,
        job_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        message: str,
    ) -> None:
        await self._prompt_run_service.append_invalid_tool_result(
            job_id=job_id,
            session_id=session_id,
            messages=messages,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            message=message,
        )

    def _reasoning_enabled(
        self,
        gateway_options: dict[str, Any],
        provider_options: dict[str, Any],
    ) -> bool:
        return self._prompt_run_service.reasoning_enabled(
            gateway_options, provider_options
        )
