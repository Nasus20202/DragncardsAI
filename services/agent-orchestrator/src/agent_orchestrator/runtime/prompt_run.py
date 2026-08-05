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
from agent_orchestrator.runtime.compaction import (
    NothingToCompactError,
    perform_compaction,
)
from agent_orchestrator.runtime.context_estimate import estimate_request
from agent_orchestrator.runtime.history_emitter import (
    SESSION_GAME_ID_KEY,
    HistoryEventEmitter,
    extract_game_id,
    is_game_id_source_tool,
    is_game_mutating_tool,
    restored_conversation_context,
)
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.personas import (
    allowed_subagent_personas,
    narrow_tool_definitions,
    persona_allowed_tools_from_snapshot,
    persona_prompt_from_snapshot,
    session_persona_snapshot,
)
from agent_orchestrator.runtime.player_agents import (
    SeatIdentity,
    build_seat_inbox_message,
    resolve_seat_identity,
    session_player_id,
    wrap_illegal_action_finding,
    wrap_player_message,
)
from agent_orchestrator.runtime.seat_guard import SeatScopeViolation, check_seat_scope
from agent_orchestrator.runtime.session_modes import is_orchestrated, session_mode
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import (
    JOB_INLINE_SKILLS_KEY,
    SkillRegistry,
    enabled_skill_assignments,
    render_prompt_with_inline_skills,
)
from agent_orchestrator.runtime.system_prompts import (
    build_subagent_system_prompt,
    build_system_prompt,
)
from agent_orchestrator.runtime.tokens import (
    count_tokens_for_text,
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
    extract_tokens_from_response,
)
from agent_orchestrator.runtime.truncation import is_output_truncated
from agent_orchestrator.storage.models import Job
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Sent as a `user` message, because that is the position the manual "continue"
# occupied — this feature automates that message and nothing else.
TURN_CONTINUATION_INSTRUCTION = (
    "Your previous message was cut off by the provider's output token limit "
    "before you finished. Continue exactly where you left off. Do not repeat "
    "what you already wrote, do not restart, and do not acknowledge this "
    "message; simply carry on."
)


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
                    # `mark_job_cancelled` appends the durable `cancellation` row
                    # and hands back its id, so the live copy goes out under that
                    # same id and the client collapses the two instead of showing
                    # one cancellation twice (DRA-34). The publish is not
                    # optional: `cancellation` is terminal, so leaving it to the
                    # stream's fallback poll holds that client's stream open for
                    # the whole idle interval (DRA-37).
                    reason = "cancelled before execution"
                    durable_event_id = await self._repository.mark_job_cancelled(
                        job.id, reason=reason
                    )
                    await self._live_event_bus.publish(
                        job.id,
                        "cancellation",
                        {"reason": reason},
                        durable_event_id=durable_event_id,
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
                    # The durable row and the live copy are the same event and
                    # now share an id, so they must carry the same payload —
                    # persisting only the code left a reload showing less than
                    # the live stream had. This matches `fail_job` below.
                    durable_event_id = await self._repository.append_event(
                        job.id, session.id, "failure", failure
                    )
                    await self._live_event_bus.publish(
                        job.id,
                        "failure",
                        failure,
                        durable_event_id=durable_event_id,
                    )
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
                # The persona snapshot was captured onto this session when the
                # child was spawned, or when this session adopted a persona of its
                # own. Either way it is read here, never the persona table, so
                # editing or deleting the persona cannot change a run in flight.
                persona_snapshot = session_persona_snapshot(session)
                if is_subagent:
                    system_prompt = build_subagent_system_prompt(
                        self._skill_registry,
                        active_skills,
                        persona_prompt=persona_prompt_from_snapshot(persona_snapshot),
                    )
                else:
                    system_prompt = build_system_prompt(
                        self._skill_registry,
                        active_skills,
                        # Only the personas this session allowlists, so the model
                        # is never told about a name the spawn guard would refuse.
                        personas=allowed_subagent_personas(session),
                        persona_prompt=persona_prompt_from_snapshot(persona_snapshot),
                    )
                all_registries = await self._repository.list_mcp_registries()
                tool_definitions = await self._mcp_tool_catalog.list_session_tools(
                    session.enabled_mcps, all_registries, ignore_failures=True
                )
                # A persona may narrow tool access and can never widen it: the
                # allowlist is applied by filtering the definitions this session
                # already resolved, and both the list offered to the model and the
                # dispatch mapping are derived from the filtered result, so an
                # excluded tool is neither advertised nor callable by name.
                tool_definitions = narrow_tool_definitions(
                    tool_definitions,
                    persona_allowed_tools_from_snapshot(persona_snapshot),
                )
                mcp_tools = self._mcp_tool_catalog.as_openai_tools(tool_definitions)
                tool_mapping = self._mcp_tool_catalog.as_mapping(tool_definitions)

                # Who this job is, resolved once from session metadata the agent
                # cannot write. ``seat_identity`` is the caller's seat when this
                # job is a player of an orchestrated game and ``None`` otherwise —
                # including for a player child of a `chat` session, which must
                # keep behaving exactly as it did before orchestrated mode.
                seat_identity = await resolve_seat_identity(
                    session, load_session=self._repository.get_session
                )
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
                    seat_identity=seat_identity,
                    session_orchestrated=is_orchestrated(session),
                    # An illegal-action finding is evidence the judge is handed
                    # rather than a violation it has to re-derive, so it is written
                    # to the durable game timeline as well as to this job.
                    history_emitter=self._history_emitter,
                    game_id=self._session_game_id(session),
                    subagent_wait_timeout_seconds=(
                        self._settings.subagent_wait_timeout_seconds
                    ),
                    subagent_wait_poll_interval_seconds=(
                        self._settings.subagent_wait_poll_interval_seconds
                    ),
                    ask_user_timeout_seconds=self._settings.ask_user_timeout_seconds,
                    ask_user_poll_interval_seconds=(
                        self._settings.ask_user_poll_interval_seconds
                    ),
                )
                tools = builtin_registry.as_openai_tools() + mcp_tools

                # The skills the prompt loaded into its own turn go in the model's
                # copy of the user message only: the stored prompt stays what the
                # user typed, so the transcript and the replay of this turn are
                # unchanged and the content costs its tokens once.
                #
                # Rendered here, ahead of auto-compaction, because the inlined
                # `SKILL.md` content is part of the request the trigger has to
                # measure — a mentioned skill can add tens of thousands of
                # tokens the trigger would otherwise never see. Only the render
                # moved: the prompt event and the `skill_loaded` announcements
                # stay below, so the transcript's ordering is unchanged.
                user_content, inlined_skills = render_prompt_with_inline_skills(
                    self._skill_registry,
                    (full_job.metadata_json or {}).get(JOB_INLINE_SKILLS_KEY) or [],
                    full_job.prompt,
                )

                if session.multi_turn_memory:
                    await self.maybe_auto_compact(
                        job.id,
                        session.id,
                        system_prompt=system_prompt,
                        tools=tools,
                        user_message=user_content,
                    )

                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                ]
                restored_context = restored_conversation_context(session)
                if restored_context:
                    messages.extend(copy.deepcopy(restored_context))
                if session.multi_turn_memory:
                    prior = await self._transcript_service.build_message_history(
                        session.id, job.id
                    )
                    messages.extend(prior)
                # A seat's out-of-band input — messages from other seats, and the
                # findings still open against it — arrives as one user-role
                # message ahead of its own prompt. Never in the system prompt:
                # player text must not occupy an instruction position, and that
                # rule is kept by construction rather than by review.
                seat_inbox = await self._collect_seat_inbox(seat_identity)
                if seat_inbox is not None:
                    messages.append(seat_inbox)
                messages.append({"role": "user", "content": user_content})
                self._emit_user_prompt_event(session=session, prompt=full_job.prompt)
                await self._announce_inlined_skills(
                    job_id=job.id, session_id=session.id, skill_names=inlined_skills
                )
                await self._repository.append_event(
                    job.id, session.id, "progress", {"status": "running"}
                )

                accumulated_job_tokens = 0
                # A turn the provider truncates is resumed rather than reported
                # as finished, so the answer arrives in segments. These hold the
                # segments and count consecutive truncations; both reset the
                # moment a round produces tool calls, because work happening is
                # evidence the model is not stuck being truncated.
                continued_segments: list[str] = []
                continuations = 0
                context_window_size: int | None = None
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
                        # As above: the durable row's id is what lets the live
                        # copy collapse into it rather than render twice.
                        reason = "cancelled during execution"
                        durable_event_id = await self._repository.mark_job_cancelled(
                            job.id, reason=reason
                        )
                        await self._live_event_bus.publish(
                            job.id,
                            "cancellation",
                            {"reason": reason},
                            durable_event_id=durable_event_id,
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
                            # A chunk carries `snapshot_event_id` in its payload
                            # rather than `durable_event_id`, because it is not a
                            # copy of a finished row: it is a growing prefix of one
                            # the client must keep replacing in place. That key is
                            # what collapses the chunks and the final row into one
                            # transcript entry; see `upsertStreamEvent`.
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
                        # "No tool calls" used to mean both "the model answered"
                        # and "the model stopped for some other reason". A
                        # response cut off at the provider's output cap has
                        # exactly this shape, so completing here reported a
                        # truncated turn as a finished one (DRA-45).
                        if is_output_truncated(response.finish_reason):
                            context_window_size = (
                                context_window_size
                                if context_window_size is not None
                                else await self._resolve_context_window(model_config)
                            )
                            if await self._continue_truncated_turn(
                                job_id=job.id,
                                session_id=session.id,
                                messages=messages,
                                response=response,
                                tools=tools,
                                continuations=continuations,
                                context_window_size=context_window_size,
                            ):
                                continued_segments.append(response.content)
                                continuations += 1
                                continue

                        logger.info(
                            "Job %s completed without further tool calls", job.id
                        )
                        job_span.set_attribute("job.status", "completed")
                        await self.complete_job(
                            full_job,
                            "".join([*continued_segments, response.content]),
                            accumulated_job_tokens,
                        )
                        return

                    # Work happened, so any earlier truncation was not the model
                    # being stuck. The segments belong to the tool-call round's
                    # assistant message from here on, not to the final answer.
                    continued_segments.clear()
                    continuations = 0

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
                        # The seat guard, before either dispatch path. A seat may
                        # act only with its own cards, and that has to hold for
                        # every tool it can reach — builtin and MCP alike — so the
                        # check sits above the split rather than inside one branch.
                        # `seat_identity` is None for the orchestrating job and for
                        # every chat-mode session, and those calls are unguarded.
                        if seat_identity is not None:
                            violation = check_seat_scope(
                                caller_player_id=seat_identity.player_id,
                                tool_name=tool_call.name,
                                arguments=tool_call.arguments,
                            )
                            if violation is not None:
                                logger.warning(
                                    "Job %s refused tool %s: seat %s named seat %s "
                                    "in argument %s",
                                    job.id,
                                    tool_call.name,
                                    seat_identity.player_id,
                                    violation.foreign_player_id,
                                    violation.argument,
                                )
                                await self.append_seat_scope_refusal(
                                    job_id=job.id,
                                    session_id=session.id,
                                    messages=messages,
                                    tool_call_id=tool_call.id,
                                    arguments=tool_call.arguments,
                                    violation=violation,
                                )
                                continue
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
                durable_event_id = await self._repository.append_event(
                    job.id,
                    session.id,
                    "completion",
                    {"text": interrupt_message},
                )
                await self._live_event_bus.publish(
                    job.id,
                    "completion",
                    {"text": interrupt_message},
                    durable_event_id=durable_event_id,
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

    async def _collect_seat_inbox(
        self, seat_identity: SeatIdentity | None
    ) -> dict[str, str] | None:
        """The out-of-band block a seat reads before its own prompt, if any.

        Two channels, in one message, in this order: the messages other seats
        sent it, then every finding still open against it.

        Messages are *delivered* here — read undelivered, then conditionally
        marked, and only the ones this call actually claimed are framed. That
        ordering is what makes delivery exactly-once: two concurrent invocations
        of the same seat both read the same rows, and the one that loses the
        conditional write frames nothing rather than replaying a message already
        in the other's context.

        Findings are the opposite: they are *not* consumed. Every open finding is
        carried into every invocation until the orchestrating agent resolves it,
        so a seat cannot outlast a violation by ignoring one turn.

        Returns ``None`` for any job that holds no seat, which is the
        orchestrating job and every job of a `chat` session.
        """
        if seat_identity is None:
            return None
        entries: list[str] = []
        try:
            pending = await self._repository.list_undelivered_player_messages(
                seat_identity.orchestrator_session_id, seat_identity.player_id
            )
            if pending:
                claimed = set(
                    await self._repository.mark_player_messages_delivered(
                        [message.id for message in pending]
                    )
                )
                entries.extend(
                    wrap_player_message(
                        sender_player_id=message.sender_player_id,
                        body=message.body,
                    )
                    for message in pending
                    if message.id in claimed
                )
            findings = await self._repository.list_open_illegal_actions(
                seat_identity.orchestrator_session_id, seat_identity.player_id
            )
            entries.extend(
                wrap_illegal_action_finding(
                    finding_id=finding.id,
                    violation=finding.violation,
                    required_undo=finding.required_undo,
                    round_number=finding.round_number,
                )
                for finding in findings
            )
        except Exception:
            # A seat that cannot read its inbox still has a turn to play, and
            # failing the job would lose the turn as well as the messages. The
            # messages that were already marked delivered are the cost of that
            # choice, which is why the marking happens as late as it does.
            logger.warning(
                "Failed to assemble the inbox for seat %s of session %s",
                seat_identity.player_id,
                seat_identity.orchestrator_session_id,
                exc_info=True,
            )
        return build_seat_inbox_message(entries)

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

    async def _announce_inlined_skills(
        self, *, job_id: str, session_id: str, skill_names: list[str]
    ) -> None:
        """Record and publish a ``skill_loaded`` event per skill the prompt loaded.

        Reusing the event the ``load_skill`` built-in emits means the transcript
        already shows "Skill loaded: <name>" for a mention, with no separate
        rendering path to keep in step.
        """
        for skill_name in skill_names:
            try:
                reference_count = len(
                    self._skill_registry.list_reference_files(skill_name)
                )
            except FileNotFoundError, OSError:
                reference_count = 0
            payload = {
                "skill_name": skill_name,
                "reference_file_count": reference_count,
            }
            durable_event_id = await self._repository.append_event(
                job_id, session_id, "skill_loaded", payload
            )
            await self._live_event_bus.publish(
                job_id, "skill_loaded", payload, durable_event_id=durable_event_id
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
        coro = emitter.emit_user_prompt(
            game_id=game_id,
            prompt=prompt,
            session_mode=session_mode(session),
        )
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

        The session's mode travels alongside the seat, and the two are not
        redundant: the orchestrating agent's own moves carry the mode with no
        seat, so a consumer can tell an orchestrated timeline from a chat one
        without reading the absence of a seat id as evidence of either.
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
            session_mode=session_mode(session),
        )
        task = asyncio.create_task(coro)
        self._history_tasks.add(task)
        task.add_done_callback(self._history_tasks.discard)

    async def record_failure(self, job: Job, failure: dict[str, Any]) -> None:
        durable_event_id = await self._repository.append_event(
            job.id, job.session.id, "failure", failure
        )
        await self._live_event_bus.publish(
            job.id, "failure", failure, durable_event_id=durable_event_id
        )
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
        payload = {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": exposed_tool_name,
            "tool_name": tool_name,
            "assignment": assignment,
            "server_url": server_url,
            "arguments": arguments,
        }
        # Published as well as persisted. A tool call is announced *before* the
        # tool runs, and a slow tool is exactly when the live bus goes quiet, so
        # a persisted-only row leaves the transcript showing nothing for the
        # whole call — previously masked by a 200 ms stream poll, and the reason
        # that poll had to be that fast. Carrying the durable id collapses the
        # live copy into the polled row instead of rendering both (DRA-34).
        durable_event_id = await self._repository.append_event(
            job_id, session_id, "tool_call", payload
        )
        await self._live_event_bus.publish(
            job_id, "tool_call", payload, durable_event_id=durable_event_id
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
        payload = {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": exposed_tool_name,
            "tool_name": tool_name,
            "assignment": assignment,
            "server_url": server_url,
            "is_error": result.get("is_error", False),
            "result": result,
        }
        # Published for the same reason as the call it answers: the bus is quiet
        # while a tool runs, so the result would otherwise wait for whatever
        # wakes the stream next.
        durable_event_id = await self._repository.append_event(
            job_id, session_id, "tool_result", payload
        )
        await self._live_event_bus.publish(
            job_id, "tool_result", payload, durable_event_id=durable_event_id
        )

    async def complete_job(
        self, job: Job, content: str, accumulated_job_tokens: int
    ) -> None:
        durable_event_id = await self._repository.append_event(
            job.id,
            job.session.id,
            "completion",
            {"text": content},
        )
        await self._live_event_bus.publish(
            job.id,
            "completion",
            {"text": content},
            durable_event_id=durable_event_id,
        )
        await self._repository.update_job_tokens_used(job.id, accumulated_job_tokens)
        await self._repository.mark_job_completed(job.id, content)
        await self._maybe_terminate_child_session(job)

    async def _resolve_context_window(self, model_config: Any) -> int:
        """The model's context window, or the configured default if unknown.

        Fetched only when a truncation actually happens, so the ordinary path
        never pays for a guard it does not reach, and cached by the caller for
        the life of the turn.
        """
        context_length: int | None = None
        try:
            context_length = await self._bifrost_client.get_model_context_length(
                model_config.provider_id, model_config.model_name
            )
        except Exception as exc:
            # A gateway that cannot answer must not be the reason a turn dies.
            # The configured default is the same fallback auto-compaction uses.
            logger.warning(
                "Could not resolve the context window for %s (%s); using the default",
                model_config.model_name,
                exc,
            )
        return context_length or self._settings.context_window_size

    async def _continue_truncated_turn(
        self,
        *,
        job_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        response: Any,
        tools: list[dict[str, Any]],
        continuations: int,
        context_window_size: int,
    ) -> bool:
        """Extend `messages` so the turn can resume, or refuse and say so.

        Returns True only when the turn should take another round. Every refusal
        path falls through to the caller's existing completion branch, so the
        worst this can do is behave exactly as it did before it existed.
        """
        max_continuations = self._settings.auto_continue_max_continuations
        if not self._settings.auto_continue_truncated_turns:
            logger.info(
                "Job %s stopped at the provider's output cap (%s); automatic "
                "continuation is disabled, so the turn is completed as it stands",
                job_id,
                response.finish_reason,
            )
            return False

        if continuations >= max_continuations:
            logger.warning(
                "Job %s truncated again (%s) after %s automatic continuation(s); "
                "the per-turn cap is reached, so the turn is completed as it stands",
                job_id,
                response.finish_reason,
                continuations,
            )
            return False

        # The request the continuation would actually send, measured after the
        # messages it would add. Growing a request that is already at the budget
        # only buys another truncation, at the price of another paid call.
        candidate = [*messages]
        if response.content:
            candidate.append({"role": "assistant", "content": response.content})
        candidate.append({"role": "user", "content": TURN_CONTINUATION_INSTRUCTION})
        estimate = estimate_tokens_for_messages(candidate) + estimate_tokens_for_tools(
            tools
        )
        budget = int(context_window_size * self._settings.context_compaction_threshold)
        if estimate >= budget:
            # Compaction cannot help: it rewrites persisted history and has no
            # effect on a message list already assembled for the turn in flight.
            logger.warning(
                "Job %s truncated (%s) but a continuation would send about %s tokens "
                "against a budget of %s; completing the turn instead",
                job_id,
                response.finish_reason,
                estimate,
                budget,
            )
            return False

        # An assistant message with empty content is rejected by some providers,
        # and a reasoning model can spend its whole output budget thinking and
        # return none. There is simply nothing to carry forward in that case.
        if response.content:
            messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": TURN_CONTINUATION_INSTRUCTION})

        logger.info(
            "Job %s stopped at the provider's output cap (%s); continuing the turn "
            "automatically (%s of %s)",
            job_id,
            response.finish_reason,
            continuations + 1,
            max_continuations,
        )
        payload = {
            "reason": "output_token_limit",
            "finish_reason": response.finish_reason,
            "continuation": continuations + 1,
            "max_continuations": max_continuations,
        }
        # Persisted and published under the durable row's id, so the live copy
        # collapses into it rather than rendering a second marker (DRA-34).
        durable_event_id = await self._repository.append_event(
            job_id, session_id, "turn_continued", payload
        )
        await self._live_event_bus.publish(
            job_id, "turn_continued", payload, durable_event_id=durable_event_id
        )
        return True

    async def maybe_auto_compact(
        self,
        job_id: str,
        session_id: str,
        *,
        system_prompt: str,
        tools: list[dict[str, Any]],
        user_message: str | None,
    ) -> None:
        """Compact the session's history when the request reaches the threshold.

        The estimate covers the request the worker is about to send, not the
        replayed history alone: the system prompt, every tool definition the
        model is offered, any conversation a restore attached to the session,
        the replay, and the current turn's user message as rendered — which is
        where a skill the prompt inlined into itself lives. The one part left
        out is the seat inbox, which cannot be measured without delivering it.

        `system_prompt`, `tools` and `user_message` are required rather than
        defaulted, because a caller that forgot one would silently go back to
        measuring less than the request — which is the defect this exists to
        fix, and it would leave no trace.

        Compaction can only shrink the replay, so a session whose pressure is
        fixed request cost is left alone rather than made to pay for a
        summarizing call that cannot lower the ratio.

        This never raises. Auto-compaction exists to keep a job inside its
        context window, so its own failure must not be the reason that job
        fails — it is called from inside the job's `try`, whose handlers mark
        the job failed. A real failure is logged and recorded as a
        `compaction_failed` event, and the job proceeds on the history it
        already has; finding nothing to summarize is not a failure at all.
        """
        ratio: float | None = None
        try:
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
                context_window_size = (
                    context_length or self._settings.context_window_size
                )

                threshold = self._settings.context_compaction_threshold

                # The same estimator the context metadata endpoint runs, over
                # the same components, so the ratio this fires on is the ratio
                # the dashboard's context widget shows for the session.
                replay_messages = await self._transcript_service.build_message_history(
                    session_id, current_job_id=job_id
                )
                # A restored conversation is prepended to every request this
                # session sends and compaction never rewrites it, so it is
                # counted with the replay rather than left out — and then
                # excluded again from what the guard treats as compactable. The
                # seat inbox is the one request component neither side counts:
                # `_collect_seat_inbox` consumes the messages it reads, so it
                # cannot be measured without delivering them.
                restored = restored_conversation_context(full_job.session)
                estimate = estimate_request(
                    system_prompt=system_prompt,
                    tools=tools,
                    replay_messages=restored + replay_messages,
                    user_message=user_message,
                    context_window_size=context_window_size,
                )
                ratio = estimate.usage_ratio

                if ratio < threshold:
                    return

                restored_tokens = (
                    estimate_tokens_for_messages(restored) if restored else 0
                )
                compactable, min_replay_tokens = await self._compactable_replay(
                    session_id, estimate.replay - restored_tokens
                )
                # Two reasons not to summarize. Either there is too little
                # history for a summary to be an improvement on it, or the
                # parts compaction cannot touch already fill the window on
                # their own, so no amount of summarizing produces a request
                # that fits. Both are fixed request cost rather than history,
                # and in both the summarizing call would be spent for nothing.
                #
                # Not covered, deliberately: a session whose fixed cost alone
                # is over the *threshold* but still under the window, with real
                # history behind it. Compaction cannot get that session back
                # under the threshold, but it does still shrink the request, so
                # it runs.
                hopeless = estimate.fixed_cost >= context_window_size
                if compactable < min_replay_tokens or hopeless:
                    logger.info(
                        "Job %s: usage ratio %.3f reaches threshold %.3f on fixed "
                        "request cost, not history — skipping compaction of session "
                        "%s (reason=%s, fixed_cost=%d, compactable_replay=%d, "
                        "floor=%d, %s)",
                        job_id,
                        ratio,
                        threshold,
                        session_id,
                        (
                            "fixed cost alone fills the window"
                            if hopeless
                            else "too little history to be worth summarizing"
                        ),
                        estimate.fixed_cost,
                        compactable,
                        min_replay_tokens,
                        estimate.as_log_fields(),
                        extra={"context_estimate": estimate.as_log_extra()},
                    )
                    return

                logger.info(
                    "Job %s: usage ratio %.3f exceeds threshold %.3f — auto-compacting "
                    "session %s (%s)",
                    job_id,
                    ratio,
                    threshold,
                    session_id,
                    estimate.as_log_fields(),
                    extra={"context_estimate": estimate.as_log_extra()},
                )

                await perform_compaction(
                    repository=self._repository,
                    bifrost_client=self._bifrost_client,
                    session_id=session_id,
                    model_config=full_job.session.model_config,
                    current_job_id=job_id,
                    live_event_bus=self._live_event_bus,
                    event_char_budget=(
                        self._settings.context_compaction_event_char_budget
                    ),
                    max_input_tokens=int(context_window_size * threshold),
                )
        except NothingToCompactError as exc:
            # Reachable on an early turn, and on a session whose only history is
            # already summarized. Nothing went wrong, so nothing is reported.
            logger.info("Job %s: nothing to compact (%s)", job_id, exc)
        except Exception as exc:
            # `CancelledError` derives from BaseException and is deliberately
            # not caught: a cancelled job must still cancel.
            logger.exception(
                "Job %s: auto-compaction failed at usage ratio %s — continuing on the existing history",
                job_id,
                f"{ratio:.3f}" if ratio is not None else "unknown",
            )
            await self._record_compaction_failure(
                job_id=job_id, session_id=session_id, exc=exc, ratio=ratio
            )

    async def _compactable_replay(
        self, session_id: str, replay_tokens: int
    ) -> tuple[int, int]:
        """What compaction could actually replace, and the size below which it should not bother.

        Compaction rewrites only the span since the last checkpoint. The
        previous summary is *also* in the replay — `build_message_history`
        prepends it as a system message and the replay windows never drop it —
        so the replay total is not the compactable part. Measuring against the
        total would make this guard unreachable for any session that had
        compacted once, and a session over the threshold on fixed cost would
        then pay for a summarizing call on every single turn.

        So the compactable part is the replay less the carried-forward summary,
        and the floor it must clear is the size of the summary that would
        replace it — the previous summary's measured token length, or the
        configured floor before there is one.

        `CompactionRecord.tokens_used` is deliberately not used as that size: it
        is the summarizing call's `total_tokens`, which counts the history that
        went in as well as the summary that came out, so it grows with the span
        and would suppress compaction exactly when the span is large.
        """
        record = await self._repository.get_latest_compaction_record(session_id)
        if record is None or not record.summary_text:
            return replay_tokens, self._settings.context_compaction_min_replay_tokens
        carried = estimate_tokens_for_messages(
            [{"role": "system", "content": record.summary_text}]
        )
        return (
            max(replay_tokens - carried, 0),
            count_tokens_for_text(record.summary_text),
        )

    async def _record_compaction_failure(
        self,
        *,
        job_id: str,
        session_id: str,
        exc: Exception,
        ratio: float | None,
    ) -> None:
        """Make a degraded compaction visible in the transcript and the stream.

        Recording the degradation must not itself fail the job, so a failure to
        persist or publish the event is logged and swallowed too.
        """
        failure = self.classify_execution_failure(exc)
        payload: dict[str, Any] = {
            "code": failure["code"],
            "message": failure["message"],
            "usage_ratio": ratio,
        }
        try:
            durable_event_id = await self._repository.append_event(
                job_id, session_id, "compaction_failed", payload
            )
            await self._live_event_bus.publish(
                job_id,
                "compaction_failed",
                payload,
                durable_event_id=durable_event_id,
            )
        except Exception:
            logger.exception(
                "Job %s: could not record the compaction failure event", job_id
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
        call_payload = {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": tool_name,
            "tool_name": tool_name,
            "assignment": None,
            "server_url": None,
            "arguments": {},
        }
        result_payload = {
            "tool_call_id": tool_call_id,
            "exposed_tool_name": tool_name,
            "tool_name": tool_name,
            "assignment": None,
            "server_url": None,
            "is_error": True,
            "result": result,
        }
        try:
            # Persisted and published together, matching the real tool-call path
            # above, so a rejected call reaches an open transcript as promptly as
            # an accepted one.
            call_event_id = await self._repository.append_event(
                job_id, session_id, "tool_call", call_payload
            )
            await self._live_event_bus.publish(
                job_id, "tool_call", call_payload, durable_event_id=call_event_id
            )
            result_event_id = await self._repository.append_event(
                job_id, session_id, "tool_result", result_payload
            )
            await self._live_event_bus.publish(
                job_id, "tool_result", result_payload, durable_event_id=result_event_id
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

    async def append_seat_scope_refusal(
        self,
        *,
        job_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        arguments: dict[str, Any],
        violation: SeatScopeViolation,
    ) -> None:
        """Record a seat-scope refusal and answer the model, without dispatching.

        Three events, in this order, and none of them optional:

        - a `tool_call` carrying the arguments the seat actually attempted, so the
          transcript shows what was tried rather than only that something was
          refused;
        - a `seat_scope_violation`, appended durably *and* published live, so the
          attempt is visible in the session timeline and to evaluation. Its
          `player_id` is the caller's own seat as the server resolved it — never a
          value read out of `arguments`, which is exactly what was refused. The
          live copy carries the durable row's id (DRA-34): the SSE stream both
          polls `list_events` and forwards the bus, so a live copy published under
          an id of its own would reach the browser as a second, undeduplicable
          event and the transcript would show the refusal twice. The published
          payload is the same object as the persisted one for the same reason — a
          reload must not show less than the live stream did;
        - a `tool_result` marked `is_error` carrying the refusal message.

        The `tool_call`/`tool_result` pair is what
        :mod:`agent_orchestrator.runtime.session_transcript` reconstructs a seat's
        replayed history from. Omitting either would leave the seat's next
        invocation with an assistant tool call that has no answer, which providers
        reject — so a refusal that recorded only the violation would break the seat
        one turn later, far from the cause.
        """
        result = {
            "is_error": True,
            "content": [{"type": "text", "text": violation.message}],
        }
        await self.append_tool_call_event(
            job_id=job_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            exposed_tool_name=violation.tool_name,
            tool_name=violation.tool_name,
            assignment=None,
            server_url=None,
            arguments=arguments,
        )
        payload = {
            "player_id": violation.caller_player_id,
            "foreign_player_id": violation.foreign_player_id,
            "tool_name": violation.tool_name,
            "argument": violation.argument,
            "value": violation.value,
            "message": violation.message,
        }
        durable_event_id = await self._repository.append_event(
            job_id, session_id, "seat_scope_violation", payload
        )
        await self._live_event_bus.publish(
            job_id,
            "seat_scope_violation",
            payload,
            durable_event_id=durable_event_id,
        )
        await self.append_tool_result_event(
            job_id=job_id,
            session_id=session_id,
            tool_call_id=tool_call_id,
            exposed_tool_name=violation.tool_name,
            tool_name=violation.tool_name,
            assignment=None,
            server_url=None,
            result=result,
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": json.dumps(result),
            }
        )

    async def _maybe_terminate_child_session(self, job: Job) -> None:
        """Terminate a disposable child's session when its job ends.

        A player seat's session is *not* disposable: it is the seat's memory for the
        length of the game, so a seat prompted again in a later round continues the
        same session. Seat sessions are terminated with the orchestrating session,
        or when the seat's configuration is deleted.
        """
        if job.parent_job_id is None:
            return
        if session_player_id(job.session) is not None:
            return
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
