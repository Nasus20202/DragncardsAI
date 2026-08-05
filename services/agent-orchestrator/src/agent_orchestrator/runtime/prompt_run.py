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
from agent_orchestrator.runtime.history_emitter import (
    SESSION_GAME_ID_KEY,
    SESSION_RESTORED_CONTEXT_KEY,
    HistoryEventEmitter,
    extract_game_id,
    is_game_id_source_tool,
    is_game_mutating_tool,
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
                # A seat's out-of-band input — messages from other seats, and the
                # findings still open against it — arrives as one user-role
                # message ahead of its own prompt. Never in the system prompt:
                # player text must not occupy an instruction position, and that
                # rule is kept by construction rather than by review.
                seat_inbox = await self._collect_seat_inbox(seat_identity)
                if seat_inbox is not None:
                    messages.append(seat_inbox)
                # The skills the prompt loaded into its own turn go in the model's
                # copy of the user message only: the stored prompt stays what the
                # user typed, so the transcript and the replay of this turn are
                # unchanged and the content costs its tokens once.
                user_content, inlined_skills = render_prompt_with_inline_skills(
                    self._skill_registry,
                    (full_job.metadata_json or {}).get(JOB_INLINE_SKILLS_KEY) or [],
                    full_job.prompt,
                )
                messages.append({"role": "user", "content": user_content})
                self._emit_user_prompt_event(session=session, prompt=full_job.prompt)
                await self._announce_inlined_skills(
                    job_id=job.id, session_id=session.id, skill_names=inlined_skills
                )
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

    def _restored_conversation_context(
        self, session: Any
    ) -> list[dict[str, Any]] | None:
        metadata = getattr(session, "metadata_json", None) or {}
        context = metadata.get(SESSION_RESTORED_CONTEXT_KEY)
        if isinstance(context, list) and context:
            return context
        return None

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

    async def maybe_auto_compact(self, job_id: str, session_id: str) -> None:
        """Compact the session's history when the replay estimate reaches the threshold.

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

                # Estimate actual replay size (same logic as context metadata endpoint)
                # so the threshold fires before the LLM receives an oversized request.
                replay_messages = await self._transcript_service.build_message_history(
                    session_id, current_job_id=job_id
                )
                tokens_used = estimate_tokens_for_messages(replay_messages)
                ratio = (
                    tokens_used / context_window_size
                    if context_window_size > 0
                    else 0.0
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
