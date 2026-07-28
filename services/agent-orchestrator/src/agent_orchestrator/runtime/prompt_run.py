from __future__ import annotations

import asyncio
import copy
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
from agent_orchestrator.runtime.history_emitter import (
    SESSION_GAME_ID_KEY,
    SESSION_RESTORED_CONTEXT_KEY,
    HistoryEventEmitter,
    extract_game_id,
    is_game_id_source_tool,
    is_game_mutating_tool,
)
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.player_agents import session_player_id
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry, enabled_skill_assignments
from agent_orchestrator.runtime.system_prompts import (
    build_subagent_system_prompt,
    build_system_prompt,
)
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
    history_emitter: HistoryEventEmitter | None = None


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
        self._history_emitter = dependencies.history_emitter
        self._transcript_service = transcript_service
        self._schedule_child_job = schedule_child_job
        self._history_tasks: set[asyncio.Task[Any]] = set()

    async def run(self, job: Job) -> None:
        with tracer.start_as_current_span(
            "agent_orchestrator.run_job",
            attributes={"job.id": job.id},
        ) as job_span:
            # Seeded so failure handling has a job to record against even when
            # the reload below is what crashed.
            full_job = job
            try:
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

                logger.info(
                    "Starting job %s for session %s with provider=%s model=%s",
                    job.id,
                    session.id,
                    model_config.provider_id,
                    model_config.model_name,
                )
                is_subagent = job.parent_job_id is not None
                active_skills = enabled_skill_assignments(session.enabled_skills)
                if is_subagent:
                    system_prompt = build_subagent_system_prompt(
                        self._skill_registry, active_skills
                    )
                else:
                    system_prompt = build_system_prompt(
                        self._skill_registry, active_skills
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
                    skill_assignments=active_skills,
                    job=full_job,
                    schedule_child_fn=self._schedule_child_job,
                    player_configs=list(session.player_configs),
                    subagent_wait_timeout_seconds=(
                        self._settings.subagent_wait_timeout_seconds
                    ),
                    subagent_wait_poll_interval_seconds=(
                        self._settings.subagent_wait_poll_interval_seconds
                    ),
                )
                tools = builtin_registry.as_openai_tools() + mcp_tools

                if session.multi_turn_memory:
                    await self.maybe_auto_compact(job.id, session.id)

                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                ]
                restored_context = self._restored_conversation_context(session)
                if restored_context:
                    messages.extend(copy.deepcopy(restored_context))
                if session.multi_turn_memory:
                    prior = await self._transcript_service.build_message_history(
                        session.id, job.id
                    )
                    messages.extend(prior)
                messages.append({"role": "user", "content": full_job.prompt})
                self._emit_user_prompt_event(session=session, prompt=full_job.prompt)
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

                        captured_game_id = await self._capture_game_id(
                            session=session,
                            assignment=tool_definition.assignment_name,
                            tool_name=tool_definition.actual_name,
                            arguments=tool_call.arguments,
                            result=result,
                        )
                        # A game-mutating tool call that returned an error did
                        # not change the game; do not record it as an agent move.
                        tool_failed = bool(result.get("is_error", False))
                        if captured_game_id is not None and not tool_failed:
                            self._emit_agent_move_event(
                                game_id=captured_game_id,
                                tool_definition=tool_definition,
                                arguments=tool_call.arguments,
                                reasoning=response.content or "",
                                messages=messages,
                                session=session,
                            )

                await self._repository.update_job_tokens_used(
                    job.id, accumulated_job_tokens
                )
                job_span.set_attribute("job.status", "interrupted")
                interrupt_message = (
                    "I reached the tool round limit before completing this task. "
                    "My partial work above is preserved in context. "
                    "Please send a follow-up message to continue."
                )
                await self._repository.append_event(
                    job.id,
                    session.id,
                    "completion",
                    {"text": interrupt_message},
                )
                await self._live_event_bus.publish(
                    job.id,
                    "completion",
                    {"text": interrupt_message},
                )
                await self._repository.mark_job_interrupted(
                    job.id, result_text=interrupt_message
                )
                await self._maybe_terminate_child_session(full_job)
                return
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
            except Exception as exc:
                # Catch-all on purpose: anything escaping here would leave the
                # job in `running`, and non-terminal jobs are excluded from
                # context replay, so the prompt that triggered the run would be
                # lost from the session transcript forever. `CancelledError`
                # derives from BaseException and is deliberately not caught.
                logger.exception("Job %s failed", job.id)
                failure = self.classify_execution_failure(exc)
                job_span.set_attribute("job.status", "failed")
                await self.record_failure(full_job, failure)
            finally:
                await self._drain_history_tasks()

    async def _drain_history_tasks(self) -> None:
        """Await any in-flight best-effort history emissions before the job ends.

        Emission is detached from the tool round (it never blocks the next LLM
        call), but we drain at job end so pending publishes complete and never
        outlive the job. Failures are swallowed by the emitter itself.
        """
        if not self._history_tasks:
            return
        pending = list(self._history_tasks)
        self._history_tasks.clear()
        await asyncio.gather(*pending, return_exceptions=True)

    def _restored_conversation_context(
        self, session: Any
    ) -> list[dict[str, Any]] | None:
        metadata = getattr(session, "metadata_json", None) or {}
        context = metadata.get(SESSION_RESTORED_CONTEXT_KEY)
        if isinstance(context, list) and context:
            return context
        return None

    def _session_game_id(self, session: Any) -> str | None:
        metadata = getattr(session, "metadata_json", None) or {}
        value = metadata.get(SESSION_GAME_ID_KEY)
        return value if isinstance(value, str) and value else None

    async def _capture_game_id(
        self,
        *,
        session: Any,
        assignment: str | None,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> str | None:
        """Resolve the game_id for this tool call and persist it on the session.

        Returns the game_id to use for emission, or None when the tool call does
        not mutate the game (and therefore should not produce an agent event).
        """
        existing = self._session_game_id(session)

        if is_game_id_source_tool(assignment, tool_name):
            extracted = extract_game_id(
                assignment=assignment,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
            )
            if extracted and extracted != existing:
                await self._persist_game_id(session, extracted)
            # Session-creating tools are not themselves game moves.
            return None

        if not is_game_mutating_tool(assignment, tool_name):
            return None

        game_id = existing or extract_game_id(
            assignment=assignment,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
        )
        if game_id is None:
            return None
        if game_id != existing:
            await self._persist_game_id(session, game_id)
        return game_id

    async def _persist_game_id(self, session: Any, game_id: str) -> None:
        metadata = dict(getattr(session, "metadata_json", None) or {})
        metadata[SESSION_GAME_ID_KEY] = game_id
        session.metadata_json = metadata
        try:
            await self._repository.update_session(session.id, metadata_json=metadata)
        except Exception:
            logger.warning(
                "Failed to persist game_id %s for session %s",
                game_id,
                getattr(session, "id", "?"),
                exc_info=True,
            )

    def _emit_user_prompt_event(self, *, session: Any, prompt: str) -> None:
        """Fire-and-forget emission of a ``user_prompt`` history event.

        The prompt is what triggered this agent turn. History events are keyed
        by the game-service session id, which the session only carries once a
        game exists (``metadata.game_id``). When there is no game yet — e.g. the
        very first prompt before any game is created — there is nothing to key
        the event by, so emission is skipped gracefully.
        """
        emitter = self._history_emitter
        if emitter is None or not emitter.enabled:
            return
        game_id = self._session_game_id(session)
        if game_id is None:
            return
        coro = emitter.emit_user_prompt(game_id=game_id, prompt=prompt)
        task = asyncio.create_task(coro)
        self._history_tasks.add(task)
        task.add_done_callback(self._history_tasks.discard)

    def _emit_agent_move_event(
        self,
        *,
        game_id: str,
        tool_definition: Any,
        arguments: dict[str, Any],
        reasoning: str,
        messages: list[dict[str, Any]],
        session: Any = None,
    ) -> None:
        """Fire-and-forget emission of an agent move/decision history event.

        When the emitting session represents a player seat in an orchestrated
        multi-player game, the move is tagged with that seat so downstream
        evaluation attributes it exactly rather than inferring it from turn
        order.
        """
        emitter = self._history_emitter
        if emitter is None or not emitter.enabled:
            return
        conversation_context = copy.deepcopy(messages)
        coro = emitter.emit_agent_move(
            game_id=game_id,
            intended_action=tool_definition.actual_name,
            reasoning=reasoning,
            arguments=dict(arguments),
            conversation_context=conversation_context,
            player=session_player_id(session) if session is not None else None,
        )
        task = asyncio.create_task(coro)
        self._history_tasks.add(task)
        task.add_done_callback(self._history_tasks.discard)

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

            threshold = self._settings.context_compaction_threshold

            # Estimate actual replay size (same logic as context metadata endpoint)
            # so the threshold fires before the LLM receives an oversized request.
            replay_messages = await self._transcript_service.build_message_history(
                session_id, current_job_id=job_id
            )
            tokens_used = estimate_tokens_for_messages(replay_messages)
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
