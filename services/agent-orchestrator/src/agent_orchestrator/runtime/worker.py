from __future__ import annotations

import asyncio
import json
import logging
from builtins import BaseExceptionGroup
from typing import Any

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError
from agent_orchestrator.integrations.mcp.client import McpClientError
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.compaction import perform_compaction
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_system_prompt
from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    extract_tokens_from_response,
)
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
    ):
        self._settings = settings
        self._repository = repository
        self._bifrost_client = bifrost_client
        self._live_event_bus = live_event_bus
        self._mcp_tool_catalog = mcp_tool_catalog
        self._skill_registry = skill_registry
        self._stop_event = asyncio.Event()
        self.is_running = False

    async def run_forever(self) -> None:
        self.is_running = True
        logger.info("Worker loop started")
        try:
            while not self._stop_event.is_set():
                with tracer.start_as_current_span("agent_orchestrator.claim_next_job"):
                    job = await self._repository.claim_next_job()
                if job is None:
                    await asyncio.sleep(self._settings.worker_poll_interval_seconds)
                    continue
                logger.info("Claimed job %s", job.id)
                await self._run_job(job)
        finally:
            self.is_running = False
            logger.info("Worker loop stopped")

    async def stop(self) -> None:
        self._stop_event.set()
        logger.info("Worker stop requested")

    async def _run_job(self, job: Job) -> None:
        with tracer.start_as_current_span(
            "agent_orchestrator.run_job",
            attributes={"job.id": job.id},
        ) as job_span:
            if await self._repository.get_job_cancellation_requested(job.id):
                logger.info("Job %s cancelled before execution", job.id)
                job_span.set_attribute("job.status", "cancelled")
                await self._repository.mark_job_cancelled(
                    job.id, reason="cancelled before execution"
                )
                return

            full_job = await self._repository.get_job(job.id)
            assert full_job is not None
            session = full_job.session
            prompt_run = full_job.prompt_run
            model_config = session.model_config
            job_span.set_attribute("session.id", session.id)
            if model_config is None:
                logger.warning("Job %s missing model configuration", job.id)
                job_span.set_attribute("job.status", "failed")
                await self._repository.append_event(
                    job.id, session.id, "failure", {"code": "missing_model_config"}
                )
                await self._repository.mark_job_failed(
                    job.id,
                    error_code="missing_model_config",
                    error_message="Session model configuration is required",
                    retryable=False,
                )
                return

            job_span.set_attribute("provider.id", model_config.provider_id)
            job_span.set_attribute("model.name", model_config.model_name)

            try:
                logger.info(
                    "Starting job %s for session %s with provider=%s model=%s",
                    job.id,
                    session.id,
                    model_config.provider_id,
                    model_config.model_name,
                )
                system_prompt = build_system_prompt(
                    self._skill_registry, session.skill_assignments
                )
                tool_definitions = await self._mcp_tool_catalog.list_session_tools(
                    full_job.session.mcp_assignments,
                    ignore_failures=True,
                )
                tools = self._mcp_tool_catalog.as_openai_tools(tool_definitions)
                tool_mapping = self._mcp_tool_catalog.as_mapping(tool_definitions)

                # Auto-compaction check before building history
                if session.multi_turn_memory:
                    await self._maybe_auto_compact(job.id, session.id)

                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                ]
                if session.multi_turn_memory:
                    prior = await build_message_history(
                        self._repository, session.id, job.id
                    )
                    messages.extend(prior)
                messages.append({"role": "user", "content": prompt_run.prompt})
                await self._repository.append_event(
                    job.id, session.id, "progress", {"status": "running"}
                )

                accumulated_job_tokens = 0
                reasoning_enabled = self._reasoning_enabled(
                    model_config.gateway_options, model_config.provider_options
                )
                logger.info(
                    "Job %s configured with %s tool(s), reasoning_enabled=%s",
                    job.id,
                    len(tools),
                    reasoning_enabled,
                )

                for _ in range(self._settings.worker_max_tool_rounds):
                    if await self._repository.get_job_cancellation_requested(job.id):
                        logger.info("Job %s cancelled during execution", job.id)
                        await self._repository.mark_job_cancelled(
                            job.id, reason="cancelled during execution"
                        )
                        return

                    # Create snapshot DB rows at the start of each round.
                    # We update them in-place as chunks arrive so a reconnecting
                    # client can always read the latest partial text from the DB.
                    reasoning_event_id: int | None = None
                    output_event_id: int | None = None
                    accumulated_reasoning: list[str] = []
                    accumulated_output: list[str] = []
                    reasoning_chunk_count = 0
                    output_chunk_count = 0
                    DB_WRITE_INTERVAL = 20  # persist to DB every N chunks

                    async def on_bifrost_delta(delta) -> None:
                        nonlocal reasoning_event_id, output_event_id
                        nonlocal reasoning_chunk_count, output_chunk_count

                        if reasoning_enabled and (
                            delta.reasoning or delta.reasoning_details
                        ):
                            logger.debug("Job %s reasoning chunk received", job.id)
                            details = [
                                {
                                    "index": detail.index,
                                    "type": detail.type,
                                    "text": detail.text,
                                    "signature": detail.signature,
                                }
                                for detail in delta.reasoning_details
                            ]
                            chunk_text = delta.reasoning or ""
                            full = "".join(accumulated_reasoning)
                            if chunk_text:
                                accumulated_reasoning.append(chunk_text)
                                reasoning_chunk_count += 1
                                full = "".join(accumulated_reasoning)
                                if reasoning_event_id is None:
                                    reasoning_event_id = (
                                        await self._repository.append_event(
                                            job.id,
                                            session.id,
                                            "reasoning",
                                            {"text": full},
                                        )
                                    )
                                elif reasoning_chunk_count % DB_WRITE_INTERVAL == 0:
                                    await self._repository.update_event(
                                        reasoning_event_id, {"text": full}
                                    )
                            await self._live_event_bus.publish(
                                job.id,
                                "reasoning",
                                {
                                    "text": full,
                                    "details": details,
                                    "stream": True,
                                    "snapshot_event_id": str(reasoning_event_id),
                                },
                            )

                        if delta.content:
                            logger.debug(
                                "Job %s text chunk received (%s chars)",
                                job.id,
                                len(delta.content),
                            )
                            accumulated_output.append(delta.content)
                            output_chunk_count += 1
                            full = "".join(accumulated_output)
                            if output_event_id is None:
                                output_event_id = await self._repository.append_event(
                                    job.id, session.id, "model_output", {"text": full}
                                )
                            elif output_chunk_count % DB_WRITE_INTERVAL == 0:
                                await self._repository.update_event(
                                    output_event_id, {"text": full}
                                )
                            await self._live_event_bus.publish(
                                job.id,
                                "model_output",
                                {
                                    "text": full,
                                    "stream": True,
                                    "snapshot_event_id": str(output_event_id),
                                },
                            )

                    with tracer.start_as_current_span(
                        "agent_orchestrator.chat_completion",
                        attributes={
                            "job.id": job.id,
                            "provider.id": model_config.provider_id,
                            "model.name": model_config.model_name,
                        },
                    ):
                        response = await self._bifrost_client.chat_completion(
                            model_config.provider_id,
                            model_config.model_name,
                            messages,
                            tools,
                            model_config.gateway_options,
                            model_config.provider_options,
                            on_delta=on_bifrost_delta,
                        )

                    # Final DB flush — write the complete accumulated text
                    if reasoning_event_id is not None and accumulated_reasoning:
                        await self._repository.update_event(
                            reasoning_event_id, {"text": "".join(accumulated_reasoning)}
                        )
                    elif accumulated_reasoning and reasoning_event_id is None:
                        await self._repository.append_event(
                            job.id,
                            session.id,
                            "reasoning",
                            {"text": "".join(accumulated_reasoning)},
                        )
                    if output_event_id is not None and accumulated_output:
                        await self._repository.update_event(
                            output_event_id, {"text": "".join(accumulated_output)}
                        )
                    elif accumulated_output and output_event_id is None:
                        await self._repository.append_event(
                            job.id,
                            session.id,
                            "model_output",
                            {"text": "".join(accumulated_output)},
                        )

                    # Track token usage from this LLM round
                    round_tokens = extract_tokens_from_response(response.raw)
                    if round_tokens is None:
                        logger.warning(
                            "Job %s: LLM response missing usage field, estimating tokens via tiktoken",
                            job.id,
                        )
                        round_tokens = estimate_tokens_for_messages(messages)
                    accumulated_job_tokens += round_tokens

                    if not response.tool_calls:
                        logger.info(
                            "Job %s completed without further tool calls", job.id
                        )
                        job_span.set_attribute("job.status", "completed")
                        await self._repository.append_event(
                            job.id,
                            session.id,
                            "completion",
                            {"text": response.content},
                        )
                        await self._repository.update_job_tokens_used(
                            job.id, accumulated_job_tokens
                        )
                        await self._repository.mark_job_completed(
                            job.id, response.content
                        )
                        return

                    assistant_message: dict[str, Any] = {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [],
                    }
                    messages.append(assistant_message)
                    for tool_call in response.tool_calls:
                        if tool_call.name not in tool_mapping:
                            raise RuntimeError(
                                f"Unknown tool requested: {tool_call.name}"
                            )
                        tool_definition = tool_mapping[tool_call.name]
                        logger.info(
                            "Job %s invoking tool %s via %s",
                            job.id,
                            tool_call.name,
                            tool_definition.server_url,
                        )
                        assistant_message["tool_calls"].append(
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.name,
                                    "arguments": json.dumps(tool_call.arguments),
                                },
                            }
                        )
                        await self._repository.append_event(
                            job.id,
                            session.id,
                            "tool_call",
                            {
                                "tool_call_id": tool_call.id,
                                "exposed_tool_name": tool_call.name,
                                "tool_name": tool_definition.actual_name,
                                "assignment": tool_definition.assignment_name,
                                "server_url": tool_definition.server_url,
                                "arguments": tool_call.arguments,
                            },
                        )
                        with tracer.start_as_current_span(
                            "agent_orchestrator.call_tool",
                            attributes={
                                "job.id": job.id,
                                "tool.name": tool_call.name,
                                "tool.assignment": tool_definition.assignment_name,
                            },
                        ):
                            result = await self._mcp_tool_catalog.call_tool(
                                tool_definition,
                                tool_call.arguments,
                                ignore_failures=True,
                            )
                        logger.info(
                            "Job %s received tool result for %s (is_error=%s)",
                            job.id,
                            tool_call.name,
                            result.get("is_error", False),
                        )
                        await self._repository.append_event(
                            job.id,
                            session.id,
                            "tool_result",
                            {
                                "tool_call_id": tool_call.id,
                                "exposed_tool_name": tool_call.name,
                                "tool_name": tool_definition.actual_name,
                                "assignment": tool_definition.assignment_name,
                                "server_url": tool_definition.server_url,
                                "is_error": result.get("is_error", False),
                                "result": result,
                            },
                        )
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result),
                            }
                        )

                await self._repository.update_job_tokens_used(
                    job.id, accumulated_job_tokens
                )
                job_span.set_attribute("job.status", "failed")
                raise RuntimeError("tool round limit exceeded")
            except BifrostError as exc:
                logger.warning(
                    "Job %s failed with bifrost error code=%s retryable=%s message=%s",
                    job.id,
                    exc.code,
                    exc.retryable,
                    str(exc),
                )
                job_span.set_attribute("job.status", "failed")
                await self._repository.append_event(
                    job.id,
                    session.id,
                    "failure",
                    {
                        "code": exc.code,
                        "message": str(exc),
                        "retryable": exc.retryable,
                    },
                )
                await self._repository.mark_job_failed(
                    job.id,
                    error_code=exc.code,
                    error_message=str(exc),
                    retryable=exc.retryable,
                )
            except (McpClientError, RuntimeError, ValueError) as exc:
                logger.exception("Job %s failed", job.id)
                error_message = self._format_execution_error(exc)
                job_span.set_attribute("job.status", "failed")
                await self._repository.append_event(
                    job.id,
                    session.id,
                    "failure",
                    {
                        "code": "execution_error",
                        "message": error_message,
                        "retryable": False,
                    },
                )
                await self._repository.mark_job_failed(
                    job.id,
                    error_code="execution_error",
                    error_message=error_message,
                    retryable=False,
                )

    async def _maybe_auto_compact(self, job_id: str, session_id: str) -> None:
        """Auto-compact context if estimated usage ratio exceeds threshold."""
        with tracer.start_as_current_span(
            "agent_orchestrator.maybe_auto_compact",
            attributes={"job.id": job_id, "session.id": session_id},
        ):
            # Fetch model config first so we can resolve the correct context window size
            full_job = await self._repository.get_job(job_id)
            if full_job is None or full_job.session.model_config is None:
                logger.warning(
                    "Job %s: cannot auto-compact — missing model config", job_id
                )
                return

            model_name = full_job.session.model_config.model_name
            context_length = await self._bifrost_client.get_model_context_length(
                full_job.session.model_config.provider_id, model_name
            )
            context_window_size = context_length or self._settings.context_window_size

            compaction = await self._repository.get_latest_compaction_record(session_id)
            after_job_id = compaction.covers_up_to_job_id if compaction else None
            tokens_used = await self._repository.get_tokens_used_since_compaction(
                session_id, after_job_id=after_job_id
            )
            threshold = self._settings.context_compaction_threshold
            ratio = (
                tokens_used / context_window_size if context_window_size > 0 else 0.0
            )

            if ratio < threshold:
                return

            logger.info(
                "Job %s: usage ratio %.3f exceeds threshold %.3f — auto-compacting session %s",
                job_id,
                ratio,
                threshold,
                session_id,
            )

            await perform_compaction(
                repository=self._repository,
                bifrost_client=self._bifrost_client,
                session_id=session_id,
                model_config=full_job.session.model_config,
                current_job_id=job_id,
                live_event_bus=self._live_event_bus,
            )

    def _format_execution_error(self, exc: Exception) -> str:
        if isinstance(exc, BaseExceptionGroup):
            nested_messages = [
                self._format_execution_error(item) for item in exc.exceptions
            ]
            nested_messages = [message for message in nested_messages if message]
            if nested_messages:
                return nested_messages[0]
        return str(exc)

    def _reasoning_enabled(
        self,
        gateway_options: dict[str, Any],
        provider_options: dict[str, Any],
    ) -> bool:
        return isinstance(gateway_options.get("reasoning"), dict) or isinstance(
            provider_options.get("reasoning"), dict
        )
