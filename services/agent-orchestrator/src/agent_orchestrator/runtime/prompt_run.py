from __future__ import annotations

import json
import logging
from builtins import BaseExceptionGroup
from dataclasses import dataclass
from typing import Any

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError
from agent_orchestrator.integrations.mcp.client import McpClientError
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.builtin_tools import build_builtin_registry
from agent_orchestrator.runtime.compaction import perform_compaction
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
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


class InvalidToolInvocationError(RuntimeError):
    def __init__(self, tool_name: str, message: str):
        super().__init__(message)
        self.tool_name = tool_name


@dataclass(frozen=True)
class PromptRunDependencies:
    settings: Settings
    repository: Repository
    bifrost_client: BifrostClient
    live_event_bus: LiveEventBus
    mcp_tool_catalog: McpToolCatalog
    skill_registry: SkillRegistry


class PromptRunService:
    def __init__(
        self,
        *,
        dependencies: PromptRunDependencies,
        transcript_service: SessionTranscriptService,
        schedule_child_job: Any,
    ):
        self._settings = dependencies.settings
        self._repository = dependencies.repository
        self._bifrost_client = dependencies.bifrost_client
        self._live_event_bus = dependencies.live_event_bus
        self._mcp_tool_catalog = dependencies.mcp_tool_catalog
        self._skill_registry = dependencies.skill_registry
        self._transcript_service = transcript_service
        self._schedule_child_job = schedule_child_job

    async def run(self, job: Job) -> None:
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
                await self._live_event_bus.publish(
                    job.id, "cancellation", {"reason": "cancelled before execution"}
                )
                await self._maybe_terminate_child_session(job)
                return

            full_job = await self._repository.get_job(job.id)
            assert full_job is not None
            session = full_job.session
            model_config = session.model_config
            job_span.set_attribute("session.id", session.id)
            if model_config is None:
                logger.warning("Job %s missing model configuration", job.id)
                job_span.set_attribute("job.status", "failed")
                failure = {
                    "code": "missing_model_config",
                    "message": "Session model configuration is required",
                    "retryable": False,
                }
                await self._repository.append_event(
                    job.id, session.id, "failure", {"code": "missing_model_config"}
                )
                await self._live_event_bus.publish(job.id, "failure", failure)
                await self._repository.mark_job_failed(
                    job.id,
                    error_code="missing_model_config",
                    error_message="Session model configuration is required",
                    retryable=False,
                )
                await self._maybe_terminate_child_session(full_job)
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
                    self._skill_registry, session.enabled_skills
                )
                all_registries = await self._repository.list_mcp_registries()
                tool_definitions = await self._mcp_tool_catalog.list_session_tools(
                    session.enabled_mcps, all_registries, ignore_failures=True
                )
                mcp_tools = self._mcp_tool_catalog.as_openai_tools(tool_definitions)
                tool_mapping = self._mcp_tool_catalog.as_mapping(tool_definitions)

                builtin_registry = build_builtin_registry(
                    skill_registry=self._skill_registry,
                    repository=self._repository,
                    live_event_bus=self._live_event_bus,
                    session_id=session.id,
                    job_id=job.id,
                    skill_assignments=session.enabled_skills,
                    job=full_job,
                    schedule_child_fn=self._schedule_child_job,
                )
                tools = builtin_registry.as_openai_tools() + mcp_tools

                if session.multi_turn_memory:
                    await self.maybe_auto_compact(job.id, session.id)

                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                ]
                if session.multi_turn_memory:
                    prior = await self._transcript_service.build_message_history(
                        session.id, job.id
                    )
                    messages.extend(prior)
                messages.append({"role": "user", "content": full_job.prompt})
                await self._repository.append_event(
                    job.id, session.id, "progress", {"status": "running"}
                )

                accumulated_job_tokens = 0
                reasoning_enabled = self.reasoning_enabled(
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
                        await self._live_event_bus.publish(
                            job.id,
                            "cancellation",
                            {"reason": "cancelled during execution"},
                        )
                        await self._maybe_terminate_child_session(full_job)
                        return

                    reasoning_event_id: int | None = None
                    output_event_id: int | None = None
                    accumulated_reasoning: list[str] = []
                    accumulated_output: list[str] = []
                    reasoning_chunk_count = 0
                    output_chunk_count = 0
                    db_write_interval = 20

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
                                elif reasoning_chunk_count % db_write_interval == 0:
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
                            elif output_chunk_count % db_write_interval == 0:
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
                        await self.complete_job(
                            full_job, response.content, accumulated_job_tokens
                        )
                        return

                    assistant_message: dict[str, Any] = {
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [],
                    }
                    messages.append(assistant_message)
                    for tool_call in response.tool_calls:
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
                        builtin = builtin_registry.get(tool_call.name)
                        if builtin is not None:
                            logger.info(
                                "Job %s invoking builtin tool %s",
                                job.id,
                                tool_call.name,
                            )
                            await self.append_tool_call_event(
                                job_id=job.id,
                                session_id=session.id,
                                tool_call_id=tool_call.id,
                                exposed_tool_name=tool_call.name,
                                tool_name=tool_call.name,
                                assignment="builtin",
                                server_url=None,
                                arguments=tool_call.arguments,
                            )
                            result = await builtin.handler(tool_call.arguments)
                            await self.append_tool_result_event(
                                job_id=job.id,
                                session_id=session.id,
                                tool_call_id=tool_call.id,
                                exposed_tool_name=tool_call.name,
                                tool_name=tool_call.name,
                                assignment="builtin",
                                server_url=None,
                                result=result,
                            )
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": json.dumps(result),
                                }
                            )
                            continue
                        if tool_call.name not in tool_mapping:
                            await self.append_invalid_tool_result(
                                job_id=job.id,
                                session_id=session.id,
                                messages=messages,
                                tool_call_id=tool_call.id,
                                tool_name=tool_call.name,
                                message=f"Unknown tool requested: {tool_call.name}",
                            )
                            continue
                        tool_definition = tool_mapping[tool_call.name]
                        logger.info(
                            "Job %s invoking tool %s via %s",
                            job.id,
                            tool_call.name,
                            tool_definition.server_url,
                        )
                        await self.append_tool_call_event(
                            job_id=job.id,
                            session_id=session.id,
                            tool_call_id=tool_call.id,
                            exposed_tool_name=tool_call.name,
                            tool_name=tool_definition.actual_name,
                            assignment=tool_definition.assignment_name,
                            server_url=tool_definition.server_url,
                            arguments=tool_call.arguments,
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
                                ignore_failures=False,
                            )
                        logger.info(
                            "Job %s received tool result for %s (is_error=%s)",
                            job.id,
                            tool_call.name,
                            result.get("is_error", False),
                        )
                        await self.append_tool_result_event(
                            job_id=job.id,
                            session_id=session.id,
                            tool_call_id=tool_call.id,
                            exposed_tool_name=tool_call.name,
                            tool_name=tool_definition.actual_name,
                            assignment=tool_definition.assignment_name,
                            server_url=tool_definition.server_url,
                            result=result,
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
                failure = self.classify_execution_failure(exc)
                logger.warning(
                    "Job %s failed with bifrost error code=%s retryable=%s message=%s",
                    job.id,
                    failure["code"],
                    failure["retryable"],
                    failure["message"],
                )
                job_span.set_attribute("job.status", "failed")
                await self.record_failure(full_job, failure)
            except (
                McpClientError,
                RuntimeError,
                ValueError,
                InvalidToolInvocationError,
            ) as exc:
                logger.exception("Job %s failed", job.id)
                failure = self.classify_execution_failure(exc)
                job_span.set_attribute("job.status", "failed")
                await self.record_failure(full_job, failure)

    async def record_failure(self, job: Job, failure: dict[str, Any]) -> None:
        await self._repository.append_event(job.id, job.session.id, "failure", failure)
        await self._live_event_bus.publish(job.id, "failure", failure)
        await self._repository.mark_job_failed(
            job.id,
            error_code=failure["code"],
            error_message=failure["message"],
            retryable=bool(failure["retryable"]),
        )
        await self._maybe_terminate_child_session(job)

    async def append_tool_call_event(
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
        await self._repository.append_event(
            job_id,
            session_id,
            "tool_call",
            {
                "tool_call_id": tool_call_id,
                "exposed_tool_name": exposed_tool_name,
                "tool_name": tool_name,
                "assignment": assignment,
                "server_url": server_url,
                "arguments": arguments,
            },
        )

    async def append_tool_result_event(
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
        await self._repository.append_event(
            job_id,
            session_id,
            "tool_result",
            {
                "tool_call_id": tool_call_id,
                "exposed_tool_name": exposed_tool_name,
                "tool_name": tool_name,
                "assignment": assignment,
                "server_url": server_url,
                "is_error": result.get("is_error", False),
                "result": result,
            },
        )

    async def complete_job(
        self, job: Job, content: str, accumulated_job_tokens: int
    ) -> None:
        await self._repository.append_event(
            job.id,
            job.session.id,
            "completion",
            {"text": content},
        )
        await self._live_event_bus.publish(
            job.id,
            "completion",
            {"text": content},
        )
        await self._repository.update_job_tokens_used(job.id, accumulated_job_tokens)
        await self._repository.mark_job_completed(job.id, content)
        await self._maybe_terminate_child_session(job)

    async def maybe_auto_compact(self, job_id: str, session_id: str) -> None:
        with tracer.start_as_current_span(
            "agent_orchestrator.maybe_auto_compact",
            attributes={"job.id": job_id, "session.id": session_id},
        ):
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

    async def append_invalid_tool_result(
        self,
        *,
        job_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        message: str,
    ) -> None:
        result = {
            "is_error": True,
            "content": [{"type": "text", "text": message}],
        }
        try:
            await self._repository.append_event(
                job_id,
                session_id,
                "tool_call",
                {
                    "tool_call_id": tool_call_id,
                    "exposed_tool_name": tool_name,
                    "tool_name": tool_name,
                    "assignment": None,
                    "server_url": None,
                    "arguments": {},
                },
            )
            await self._repository.append_event(
                job_id,
                session_id,
                "tool_result",
                {
                    "tool_call_id": tool_call_id,
                    "exposed_tool_name": tool_name,
                    "tool_name": tool_name,
                    "assignment": None,
                    "server_url": None,
                    "is_error": True,
                    "result": result,
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": json.dumps(result),
                }
            )
        except Exception as exc:
            raise InvalidToolInvocationError(tool_name, message) from exc

    async def _maybe_terminate_child_session(self, job: Job) -> None:
        if job.parent_job_id is not None:
            try:
                await self._repository.terminate_session(job.session.id)
            except Exception:
                logger.exception(
                    "Failed to terminate child session %s for job %s",
                    job.session.id,
                    job.id,
                )

    def format_execution_error(self, exc: Exception) -> str:
        if isinstance(exc, BaseExceptionGroup):
            nested_messages = [
                self.format_execution_error(item) for item in exc.exceptions
            ]
            nested_messages = [message for message in nested_messages if message]
            if nested_messages:
                return nested_messages[0]
        return str(exc)

    def classify_execution_failure(self, exc: Exception) -> dict[str, Any]:
        if isinstance(exc, BifrostError):
            return {
                "code": exc.code,
                "message": str(exc),
                "retryable": exc.retryable,
            }
        if isinstance(exc, McpClientError):
            return {
                "code": "mcp_transport_error",
                "message": self.format_execution_error(exc),
                "retryable": True,
            }
        if isinstance(exc, InvalidToolInvocationError):
            return {
                "code": "invalid_tool_feedback_error",
                "message": self.format_execution_error(exc),
                "retryable": False,
            }
        return {
            "code": "execution_error",
            "message": self.format_execution_error(exc),
            "retryable": False,
        }

    def reasoning_enabled(
        self,
        gateway_options: dict[str, Any],
        provider_options: dict[str, Any],
    ) -> bool:
        return isinstance(gateway_options.get("reasoning"), dict) or isinstance(
            provider_options.get("reasoning"), dict
        )
