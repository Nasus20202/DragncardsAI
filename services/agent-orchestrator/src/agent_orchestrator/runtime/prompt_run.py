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
from agent_orchestrator.runtime.builtin_tools import (
    _announce_illegal_action_finding,
    build_builtin_registry,
)
from agent_orchestrator.runtime.compaction import (
    NothingToCompactError,
    perform_compaction,
)
from agent_orchestrator.runtime.context_estimate import estimate_request
from agent_orchestrator.runtime.game_session_guard import (
    GameSessionBindingViolation,
    check_game_session_binding,
)
from agent_orchestrator.runtime.history_emitter import (
    MarvelLcgOptionIdentity,
    SESSION_GAME_ID_KEY,
    SESSION_PLATFORM_KEY,
    SESSION_RESTORED_CONTEXT_KEY,
    HistoryEventEmitter,
    extract_game_id_from_arguments,
    extract_game_id_from_result,
    extract_game_id,
    extract_game_platform,
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
from agent_orchestrator.runtime.platforms import (
    PLATFORM_MARVEL_LCG,
    platform_tool_sets,
    session_platform,
)
from agent_orchestrator.runtime.player_agents import (
    SeatIdentity,
    build_seat_inbox_message,
    resolve_seat_identity,
    session_orchestrator_session_id,
    session_player_id,
    wrap_illegal_action_finding,
    wrap_player_message,
)
from agent_orchestrator.runtime.seat_guard import SeatScopeViolation, check_seat_scope
from agent_orchestrator.runtime.seat_turn_guard import (
    PHASE_UNKNOWN,
    TurnAuthorityViolation,
    check_turn_authority,
)
from agent_orchestrator.runtime.session_dispatch_lock import SessionDispatchLock
from agent_orchestrator.runtime.session_modes import is_orchestrated, session_mode
from agent_orchestrator.runtime.skills import (
    JOB_INLINE_SKILLS_KEY,
    SkillRegistry,
    enabled_skill_assignments,
    render_prompt_with_inline_skills,
)
from agent_orchestrator.runtime.subagent_failsafes import (
    SubagentFailsafe,
    SubagentFailsafeError,
)
from agent_orchestrator.runtime.system_prompts import (
    build_subagent_system_prompt,
    build_system_prompt,
)
from agent_orchestrator.runtime.tokens import (
    count_tokens_for_text,
    estimate_tokens_for_messages,
    extract_tokens_from_response,
)
from agent_orchestrator.runtime.truncation import is_output_truncated
from agent_orchestrator.storage.models import Job
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _decoded_values(value: Any):
    """Yield dictionaries/lists represented by an MCP tool result.

    MCP results reach the prompt loop as JSON text nested inside the standard
    ``content`` list. Keeping this decoder local to the runtime lets option
    identity extraction consume both the normal wire shape and the compact
    test/fake shape without treating model-supplied tool arguments as facts.
    """
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except TypeError, ValueError:
            return
        if decoded != value:
            yield from _decoded_values(decoded)
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _decoded_values(child)
        return
    if isinstance(value, list):
        yield value
        for child in value:
            yield from _decoded_values(child)


def _option_id(value: Any) -> str | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and value != "":
        return value
    return None


def _option_field(option: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in option:
            return option[name]
    return None


def _tool_call_names(messages: list[dict[str, Any]]) -> dict[str, str]:
    names: dict[str, str] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            call_id = tool_call.get("id")
            function = tool_call.get("function")
            name = function.get("name") if isinstance(function, dict) else None
            if isinstance(call_id, str) and isinstance(name, str):
                names[call_id] = name
    return names


def _is_list_game_options_tool(name: str | None) -> bool:
    return name == "list_game_options" or bool(
        name and name.endswith("_list_game_options")
    )


def _successful_tool_result_values(message: dict[str, Any]):
    """Yield only data from a successful MCP tool result."""
    raw_content = message.get("content")
    decoded_content = next(iter(_decoded_values(raw_content)), None)
    if isinstance(decoded_content, dict):
        if decoded_content.get("is_error") is True:
            return
        result_content = decoded_content.get("content")
        if result_content is not None:
            yield from _decoded_values(result_content)
            return
    yield from _decoded_values(raw_content)


def extract_marvel_lcg_option_identity(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    messages: list[dict[str, Any]],
) -> MarvelLcgOptionIdentity | None:
    """Extract the producer's full identity for a submitted marvel-lcg option.

    The model chooses an ``option_id``; its name and prompt event are facts from
    the preceding successful ``list_game_options`` result. The result is matched
    by tool-call id, and an identity is emitted only when all three producer
    fields are present. The model's arguments alone can never supply metadata.
    """
    if tool_name != "choose_game_option":
        return None
    selected_id = _option_id(_option_field(arguments, "option_id", "optionId"))
    if selected_id is None:
        return None

    tool_call_names = _tool_call_names(messages)
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        tool_call_id = message.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not _is_list_game_options_tool(
            tool_call_names.get(tool_call_id)
        ):
            continue
        for value in _successful_tool_result_values(message):
            if not isinstance(value, dict):
                continue
            options = _option_field(value, "options", "game_options", "gameOptions")
            if not isinstance(options, list):
                continue
            for option in options:
                if not isinstance(option, dict):
                    continue
                candidate_id = _option_id(
                    _option_field(option, "option_id", "optionId", "id")
                )
                if candidate_id != selected_id:
                    continue
                name = _option_field(option, "name", "option_name", "optionName")
                option_event = _option_field(option, "event", "event_name", "eventName")
                resolved_event = option_event
                if not isinstance(resolved_event, str) or not resolved_event.strip():
                    resolved_event = _option_field(
                        value, "event", "event_name", "eventName"
                    )
                if (
                    isinstance(name, str)
                    and name.strip()
                    and isinstance(resolved_event, str)
                    and resolved_event.strip()
                ):
                    return {
                        "id": candidate_id,
                        "name": name,
                        "event": resolved_event,
                    }
    return None


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
    session_dispatch_lock: SessionDispatchLock | None = None


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
        self._session_dispatch_lock = dependencies.session_dispatch_lock
        self._transcript_service = transcript_service
        self._schedule_child_job = schedule_child_job
        self._history_tasks: set[asyncio.Task[Any]] = set()

    async def run(self, job: Job) -> None:
        if self._session_dispatch_lock is None:
            await self._run_unserialized(job)
            return
        async with self._session_dispatch_lock.for_session(job.session_id):
            await self._run_unserialized(job)

    async def _run_unserialized(self, job: Job) -> None:
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
                # A subagent gets the three failsafes (DRA-51): an absolute
                # deadline, a repeated-error counter, and an empty-response
                # counter. Top-level jobs never construct one, so their run
                # keeps exactly the behaviour it had before the failsafes
                # existed.
                failsafe = None
                if is_subagent:
                    failsafe = SubagentFailsafe(
                        timeout_seconds=self._settings.subagent_timeout_seconds,
                        max_consecutive_errors=(
                            self._settings.subagent_failsafe_max_consecutive_errors
                        ),
                        max_empty_responses=(
                            self._settings.subagent_failsafe_max_empty_responses
                        ),
                    )
                active_skills = enabled_skill_assignments(session.enabled_skills)
                # Who this job is, resolved once from session metadata the agent
                # cannot write. ``seat_identity`` is the caller's seat when this
                # job is a player of an orchestrated game and ``None`` otherwise —
                # including for a player child of a `chat` session, which must
                # keep behaving exactly as it did before orchestrated mode.
                seat_identity = await resolve_seat_identity(
                    session, load_session=self._repository.get_session
                )
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
                        platform=session_platform(session),
                        player_session=seat_identity is not None,
                    )
                else:
                    system_prompt = build_system_prompt(
                        self._skill_registry,
                        active_skills,
                        # Only the personas this session allowlists, so the model
                        # is never told about a name the spawn guard would refuse.
                        personas=allowed_subagent_personas(session),
                        persona_prompt=persona_prompt_from_snapshot(persona_snapshot),
                        platform=session_platform(session),
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
                    platform=session_platform(session),
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

                    if failsafe is not None:
                        failsafe.check_timeout()

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

                    try:
                        with tracer.start_as_current_span(
                            "agent_orchestrator.chat_completion",
                            attributes={
                                "job.id": job.id,
                                "provider.id": model_config.provider_id,
                                "model.name": model_config.model_name,
                            },
                        ):
                            chat_call = self._bifrost_client.chat_completion(
                                model_config.provider_id,
                                model_config.model_name,
                                messages,
                                tools,
                                model_config.gateway_options,
                                model_config.provider_options,
                                on_delta=on_bifrost_delta,
                            )
                            if failsafe is not None:
                                # The deadline bounds the call itself, so a
                                # provider that hangs is cancelled when the
                                # budget is spent rather than holding the
                                # worker (DRA-51).
                                response = await asyncio.wait_for(
                                    chat_call, timeout=failsafe.remaining_seconds()
                                )
                            else:
                                response = await chat_call
                    except asyncio.TimeoutError:
                        # Either the bounded call above spent the whole budget,
                        # or a provider raised its own timeout. Both mean "no
                        # response within budget"; `check_timeout` turns that
                        # into the failsafe only when the budget really is
                        # spent, so a provider timeout that landed early keeps
                        # its existing classification.
                        if failsafe is None:
                            raise
                        failsafe.check_timeout()
                        raise
                    except (BifrostError, McpClientError) as exc:
                        if failsafe is None:
                            raise
                        # A subagent's model-call failure is counted by error
                        # code instead of ending the run, so a repeating
                        # transport failure is detected as an error loop after
                        # three identical codes rather than failing on the
                        # first blip (DRA-51).
                        failure = self.classify_execution_failure(exc)
                        failsafe.note_model_error(
                            failure["code"], message=failure["message"]
                        )
                        logger.warning(
                            "Job %s subagent model-call failure code=%s; "
                            "the run continues and will fail on the third "
                            "identical code",
                            job.id,
                            failure["code"],
                        )
                        continue

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

                    if failsafe is not None:
                        # Counts the response against the no-progress and error
                        # streaks; raises `subagent_no_progress` on the third
                        # consecutive empty response (DRA-51).
                        failsafe.note_response(response)

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

                        if failsafe is not None and failsafe.is_empty(response):
                            # An empty, non-truncated answer is not a
                            # completion for a subagent: it is the no-progress
                            # condition, counted by `note_response` above and
                            # failed after three consecutive ones. Reaching
                            # here the streak is below the cap, so the run
                            # loops back to the model instead of completing
                            # with nothing (DRA-51).
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
                        # Bind every existing-game call before any seat or turn
                        # preflight can read state and before the MCP client sees
                        # the requested session_id. An unbound session is allowed
                        # its first discovery call; `_capture_game_id` persists
                        # that successful target below.
                        definition = tool_mapping.get(tool_call.name)
                        if definition is not None:
                            binding_violation = check_game_session_binding(
                                assignment=definition.assignment_name,
                                tool_name=definition.actual_name,
                                arguments=tool_call.arguments,
                                bound_game_id=self._session_game_id(session),
                            )
                            if binding_violation is not None:
                                logger.warning(
                                    "Job %s refused game-session binding for tool %s",
                                    job.id,
                                    tool_call.name,
                                )
                                await self.append_game_session_binding_refusal(
                                    job_id=job.id,
                                    session_id=session.id,
                                    messages=messages,
                                    tool_call_id=tool_call.id,
                                    arguments=tool_call.arguments,
                                    violation=binding_violation,
                                )
                                continue

                        # The seat guard, before either dispatch path. A seat may
                        # act only with its own cards, and that has to hold for
                        # every tool it can reach — builtin and MCP alike — so the
                        # check sits above the split rather than inside one branch.
                        # `seat_identity` is None for the orchestrating job and for
                        # every chat-mode session, and those calls are unguarded.
                        if seat_identity is not None:
                            platform = session_platform(session)
                            definition = tool_mapping.get(tool_call.name)
                            actual_tool_name = (
                                definition.actual_name
                                if definition is not None
                                else tool_call.name
                            )
                            game_state = None
                            if (
                                platform == PLATFORM_MARVEL_LCG
                                and actual_tool_name == "choose_game_option"
                            ):
                                game_id = self._session_game_id(session)
                                if game_id is not None:
                                    game_state = await self._read_game_state(
                                        game_id, tool_mapping
                                    )
                            violation = check_seat_scope(
                                caller_player_id=seat_identity.player_id,
                                tool_name=tool_call.name,
                                arguments=tool_call.arguments,
                                platform=platform,
                                game_state=game_state,
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
                        # Turn and phase authority, detected after the fact
                        # (DRA-62). The seat guard above answers *whose* cards a
                        # call touches and refuses before dispatch; this answers
                        # *when* and refuses nothing — a seat that advances the
                        # phase, or acts outside the player phase, gets a finding
                        # recorded against it instead, through the same DRA-30
                        # illegal-action store the coordinator and the judge
                        # already read. Like the seat guard, it applies only to
                        # seat jobs; the orchestrating job holds no seat.
                        if seat_identity is not None:
                            detected = await self._detect_turn_authority_violation(
                                session=session,
                                seat_identity=seat_identity,
                                exposed_tool_name=tool_call.name,
                                tool_mapping=tool_mapping,
                                platform=session_platform(session),
                            )
                            if detected is not None:
                                turn_violation, round_number = detected
                                await self._record_turn_authority_finding(
                                    job=job,
                                    session=session,
                                    seat_identity=seat_identity,
                                    violation=turn_violation,
                                    round_number=round_number,
                                    platform=session_platform(session),
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
                            marvel_lcg_option = None
                            if session_platform(session) == PLATFORM_MARVEL_LCG:
                                marvel_lcg_option = extract_marvel_lcg_option_identity(
                                    tool_name=tool_definition.actual_name,
                                    arguments=tool_call.arguments,
                                    messages=messages,
                                )
                            self._emit_agent_move_event(
                                game_id=captured_game_id,
                                tool_definition=tool_definition,
                                arguments=tool_call.arguments,
                                reasoning=response.content or "",
                                messages=messages,
                                session=session,
                                prompt=full_job.prompt,
                                job_id=job.id,
                                parent_job_id=job.parent_job_id,
                                marvel_lcg_option=marvel_lcg_option,
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
            except SubagentFailsafeError as exc:
                # A failsafe ends a subagent that would otherwise hang
                # (DRA-51). Recorded through the ordinary failure path so the
                # job, the event, the parent's wait and the child monitor all
                # see the same definitive outcome.
                logger.warning(
                    "Job %s ended by subagent failsafe code=%s message=%s",
                    job.id,
                    exc.error_code,
                    exc.message,
                )
                job_span.set_attribute("job.status", "failed")
                await self.record_failure(full_job, exc.as_failure())
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
            if result.get("is_error", False):
                return None
            argument_game_id = extract_game_id_from_arguments(
                assignment=assignment,
                arguments=arguments,
            )
            result_game_id = extract_game_id_from_result(
                assignment=assignment,
                tool_name=tool_name,
                result=result,
            )
            if argument_game_id is not None and result_game_id is not None:
                if argument_game_id != result_game_id:
                    return None
            replay_rebind = (
                existing is not None
                and is_orchestrated(session)
                and tool_name == "create_game"
                and result_game_id is not None
                and result_game_id != existing
            )
            if (
                existing is not None
                and not replay_rebind
                and (
                    argument_game_id not in (None, existing)
                    or result_game_id not in (None, existing)
                )
            ):
                return None
            extracted = result_game_id or argument_game_id
            if extracted:
                await self._persist_game_id(
                    session,
                    extracted,
                    platform=extract_game_platform(
                        assignment=assignment,
                        tool_name=tool_name,
                        result=result,
                        arguments=arguments,
                        expected_game_id=extracted,
                    ),
                    rotate_player_sessions=replay_rebind,
                )
            # Session-creating tools are not themselves game moves.
            return None

        if not is_game_mutating_tool(assignment, tool_name):
            if result.get("is_error", False):
                return None

            argument_game_id = extract_game_id_from_arguments(
                assignment=assignment,
                arguments=arguments,
            )
            result_game_id = extract_game_id_from_result(
                assignment=assignment,
                tool_name=tool_name,
                result=result,
            )
            if argument_game_id is not None and result_game_id is not None:
                if argument_game_id != result_game_id:
                    return None
            if existing is not None and (
                argument_game_id not in (None, existing)
                or result_game_id not in (None, existing)
            ):
                return None

            # A follow-up session may begin with a read-only state call against
            # a game that was created elsewhere. Capture its target before the
            # next model round so a subsequent ``choose_game_option`` is guarded,
            # identified, and stamped as marvel-lcg rather than using the legacy
            # DragnCards default.
            game_id = existing or result_game_id or argument_game_id
            if game_id is None:
                return None
            platform = extract_game_platform(
                assignment=assignment,
                tool_name=tool_name,
                result=result,
                arguments=arguments,
                expected_game_id=game_id,
            )
            if game_id != existing or platform is not None:
                await self._persist_game_id(session, game_id, platform=platform)
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

    async def _persist_game_id(
        self,
        session: Any,
        game_id: str,
        *,
        platform: str | None = None,
        rotate_player_sessions: bool = False,
    ) -> None:
        metadata = dict(getattr(session, "metadata_json", None) or {})
        changed = False
        if metadata.get(SESSION_GAME_ID_KEY) != game_id:
            metadata[SESSION_GAME_ID_KEY] = game_id
            changed = True
        if platform is not None and metadata.get(SESSION_PLATFORM_KEY) != platform:
            metadata[SESSION_PLATFORM_KEY] = platform
            changed = True
        if not changed:
            return
        session.metadata_json = metadata
        try:
            if rotate_player_sessions:
                updated = await self._repository.replace_game_binding(
                    session.id,
                    game_id,
                    platform=platform,
                    metadata_json=metadata,
                )
            else:
                updated = await self._repository.update_session(
                    session.id,
                    preserve_metadata_keys={
                        SESSION_GAME_ID_KEY,
                        SESSION_PLATFORM_KEY,
                        SESSION_RESTORED_CONTEXT_KEY,
                    },
                    metadata_json=metadata,
                )
            if updated is None:
                return
            session.metadata_json = updated.metadata_json
            if rotate_player_sessions:
                old_child_ids = await self._repository.reset_player_agent_sessions(
                    session.id
                )
                for child_id in old_child_ids:
                    await self._repository.terminate_session(child_id)
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
            platform=session_platform(session),
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
        prompt: str | None = None,
        job_id: str | None = None,
        parent_job_id: str | None = None,
        marvel_lcg_option: MarvelLcgOptionIdentity | None = None,
    ) -> None:
        """Fire-and-forget emission of an agent move/decision history event.

        When the emitting session represents a player seat in an orchestrated
        multi-player game, the move is tagged with that seat so downstream
        evaluation attributes it exactly rather than inferring it from turn
        order. The parent prompt is also carried as server-set provenance when
        this is a child move, allowing evaluators to distinguish coordinator
        context from a seat's untrusted report.

        The session's mode travels alongside the seat, and the two are not
        redundant: the orchestrating agent's own moves carry the mode with no
        seat, so a consumer can tell an orchestrated timeline from a chat one
        without reading the absence of a seat id as evidence of either.
        """
        emitter = self._history_emitter
        if emitter is None or not emitter.enabled:
            return
        conversation_context = copy.deepcopy(messages)
        prompt_provenance: dict[str, str] | None = None
        orchestrator_session_id = (
            session_orchestrator_session_id(session) if session is not None else None
        )
        if (
            orchestrator_session_id
            and isinstance(prompt, str)
            and prompt.strip()
            and isinstance(job_id, str)
            and job_id.strip()
            and isinstance(parent_job_id, str)
            and parent_job_id.strip()
        ):
            prompt_provenance = {
                "source": "coordinator",
                "prompt": prompt,
                "orchestrator_session_id": orchestrator_session_id,
                "parent_job_id": parent_job_id,
                "child_job_id": job_id,
            }
        emit_kwargs: dict[str, Any] = {
            "game_id": game_id,
            "intended_action": tool_definition.actual_name,
            "reasoning": reasoning,
            "arguments": dict(arguments),
            "conversation_context": conversation_context,
            "player": session_player_id(session) if session is not None else None,
            "session_mode": session_mode(session),
            "platform": session_platform(session),
            "marvel_lcg_option": marvel_lcg_option,
        }
        # DRA-85 adds this optional field to HistoryEventEmitter. Keep the
        # kwargs conditional so ordinary moves omit it entirely.
        if prompt_provenance is not None:
            emit_kwargs["prompt_provenance"] = prompt_provenance
        coro = emitter.emit_agent_move(**emit_kwargs)
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
        estimate = estimate_request(
            system_prompt="",
            tools=tools,
            replay_messages=candidate,
            context_window_size=context_window_size,
        ).total
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

    async def append_game_session_binding_refusal(
        self,
        *,
        job_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        arguments: dict[str, Any],
        violation: GameSessionBindingViolation,
    ) -> None:
        """Answer a cross-game call without forwarding it to game-service.

        The tool-call/result pair keeps the conversation replayable just like
        other locally refused calls. The refusal deliberately carries no target
        game response or identifier, so an attempted cross-game read cannot
        disclose that game's state.
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

    async def _detect_turn_authority_violation(
        self,
        *,
        session: Any,
        seat_identity: SeatIdentity,
        exposed_tool_name: str,
        tool_mapping: dict[str, Any],
        platform: str,
    ) -> tuple[TurnAuthorityViolation, int | None] | None:
        """The turn-authority violation a seat's call commits, if any.

        Cheap by construction: the common path — builtins, read-only tools,
        lifecycle tools, and every tool that is not a game-service tool — returns
        before anything touches the network. Only a phase-advancing or
        seat-action game-service tool from a seat reads game state, and that read
        is best-effort: an unreachable game-service, a session with no game
        attached, or an unreadable step id means no finding, never a failed job.

        Returns ``(violation, round_number)`` so the finding records the round
        the violation happened in, from the same neutral state read.
        """
        definition = tool_mapping.get(exposed_tool_name)
        if definition is None or definition.assignment_name != "game-service":
            return None
        tool_name = definition.actual_name
        tool_sets = platform_tool_sets(platform)
        if (
            tool_name not in tool_sets.phase_advancing
            and tool_name not in tool_sets.seat_actions
        ):
            return None
        game_id = self._session_game_id(session)
        if game_id is None:
            return None
        step = await self._read_game_step(game_id, tool_mapping)
        if step is None:
            return None
        violation = check_turn_authority(
            caller_player_id=seat_identity.player_id,
            tool_name=tool_name,
            step_id=step["step_id"],
            phase=step["phase"],
            phase_label=step["phase_label"],
            pending_seats=step["pending_seats"],
            platform=platform,
        )
        if violation is None:
            return None
        return violation, step["round_number"]

    async def _read_game_step(
        self, game_id: str, tool_mapping: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The neutral phase and opaque step data from game state, or ``None``.

        Uses the same game-service ``get_game_state`` tool the session already
        holds — the state-read mechanism that exists — rather than a second
        client or a new configuration. ``ignore_failures=True`` is what makes
        the whole read best-effort: a game-service that cannot be reached
        degrades to no finding instead of failing the seat's job.
        """
        state = await self._read_game_state(game_id, tool_mapping)
        if state is None:
            return None
        step_id = state.get("stepId")
        play_round = state.get("playRound")
        phase = state.get("phase")
        if not isinstance(phase, str):
            phase = PHASE_UNKNOWN
        pending_seats = state.get("pendingSeats")
        if not isinstance(pending_seats, list):
            pending_seats = None
        return {
            "step_id": step_id if step_id is not None else None,
            "phase": phase,
            "phase_label": (
                state.get("phaseLabel")
                if isinstance(state.get("phaseLabel"), str)
                else None
            ),
            "pending_seats": pending_seats,
            "round_number": (
                play_round
                if isinstance(play_round, int) and not isinstance(play_round, bool)
                else None
            ),
        }

    async def _read_game_state(
        self, game_id: str, tool_mapping: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Read the neutral game state through the session's game-service tool."""

        state_tool = next(
            (
                definition
                for definition in tool_mapping.values()
                if definition.assignment_name == "game-service"
                and definition.actual_name == "get_game_state"
            ),
            None,
        )
        if state_tool is None:
            return None
        result = await self._mcp_tool_catalog.call_tool(
            state_tool, {"session_id": game_id}, ignore_failures=True
        )
        if result.get("is_error"):
            return None
        content = result.get("content") or []
        if not content:
            return None
        item = content[0]
        if isinstance(item, dict) and "text" in item:
            try:
                item = json.loads(item["text"])
            except TypeError, ValueError:
                return None
        if not isinstance(item, dict):
            return None
        state = item.get("state")
        return state if isinstance(state, dict) else None

    async def _record_turn_authority_finding(
        self,
        *,
        job: Job,
        session: Any,
        seat_identity: SeatIdentity,
        violation: TurnAuthorityViolation,
        round_number: int | None,
        platform: str,
    ) -> None:
        """Record a detected turn-authority violation through the DRA-30 store.

        This is the same dispatch site the ``report_illegal_action`` built-in
        uses: the finding is a row on the orchestrating session (so it reaches
        the seat's inbox and the coordinator's stream), and announcing it writes
        the durable ``job_events`` row, the live copy under the durable id, and
        the ``illegal_action`` history event the judge reads. The seat cannot
        close it — resolution is the coordinator's, after verifying against game
        state, exactly as for a reported finding.
        """
        game_id = self._session_game_id(session)
        finding = await self._repository.open_illegal_action(
            seat_identity.orchestrator_session_id,
            player_id=seat_identity.player_id,
            violation=violation.message,
            required_undo=violation.required_undo,
            round_number=round_number,
        )
        if finding is None:
            return
        await _announce_illegal_action_finding(
            repository=self._repository,
            live_event_bus=self._live_event_bus,
            session_id=seat_identity.orchestrator_session_id,
            job_id=job.parent_job_id or job.id,
            finding=finding,
            history_emitter=self._history_emitter,
            game_id=game_id,
            platform=platform,
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
