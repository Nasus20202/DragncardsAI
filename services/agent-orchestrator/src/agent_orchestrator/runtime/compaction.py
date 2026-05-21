"""Compaction service: summarizes session history into a CompactionRecord."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agent_orchestrator.runtime.memory import build_message_history
from agent_orchestrator.runtime.tokens import (
    count_tokens_for_text,
    extract_tokens_from_response,
    estimate_tokens_for_messages,
)
from agent_orchestrator.storage.models import CompactionRecord

if TYPE_CHECKING:
    from agent_orchestrator.integrations.bifrost import BifrostClient
    from agent_orchestrator.runtime.live_events import LiveEventBus
    from agent_orchestrator.storage.models import SessionModelConfig
    from agent_orchestrator.storage.repository import Repository

logger = logging.getLogger(__name__)

COMPACTION_SYSTEM_PROMPT = """\
You are compressing an AI agent session history into a compact summary to free up context window space.
The session may involve any domain: a card game, a board game, a coding task, a research session, or anything else.

Your goal is to produce a summary dense enough for a future AI agent to resume work seamlessly,
without needing to re-read the original conversation. Assume the future agent has zero prior memory —
everything it needs to continue correctly must be present in your output.

## What to ALWAYS preserve

### Current state snapshot
Capture the exact current value of every tracked object, entity, or resource. For each one record:
- Its name or identifier
- Every meaningful attribute (numeric values, status flags, modes, configurations — not just the ones that changed)
- Any modifiers, attachments, or tokens currently applied to it
- Its relationship to other entities if that relationship affects future decisions

Also record:
- The current phase, stage, step, or mode of the overall process
- Any timer, counter, or threshold that is being tracked and its current value
- The current objective or goal the agent is working toward

### Pending work and open questions
- Every decision that has not yet been made, with the options still in play
- Any branching path or conditional that is unresolved
- Tasks that were started but not completed, and what remains to finish them
- Commitments or plans the agent made that have not yet been acted on

### Recent activity
- What was accomplished in the most recently completed unit of work (turn, task, iteration, request, etc.)
- The specific outcome: what changed, what was produced, what was confirmed
- Any errors, failures, or unexpected results, and whether they were resolved or are still outstanding
- What the agent was about to do next when the history ends (if determinable)

### Decisions and rationale
- Key choices made during the session and the core reason each was chosen
- Alternatives that were explicitly considered and rejected, and why
- Assumptions the agent made that are not derivable from stated facts
- Any user instructions or preferences stated during the session that constrain future behavior

### Accumulated context
- Tool calls whose results were non-obvious, surprising, or directly shaped a subsequent decision —
  include the tool name, a brief description of what was asked, and the key result
- Data, content, or artifacts created or retrieved that are still relevant (files written, IDs returned,
  search results used, etc.) — include enough detail that the future agent can reference or reproduce them
- External identifiers, resource names, URLs, or references that will be needed going forward
- Any facts learned about the environment, system, or domain that were not known at session start

## What to OMIT

- Step-by-step reasoning or internal monologue that led to a state that is already captured above —
  once the outcome is recorded, the path to it is not needed
- Tool call traces for operations whose full result is already reflected in the current state snapshot
  (e.g., a tool call that set a value that is now listed under current state)
- Repetitive status updates that were superseded by a later update on the same entity
- Raw verbose outputs (long lists, full file contents, large JSON blobs) when a concise summary of the
  key facts extracted from them is sufficient
- Exploratory reasoning or plans that were abandoned without producing a result
- Filler phrases, hedging, meta-commentary about the summary itself

## Format instructions

- Output plain text only; no markdown headers, bullets, or code blocks unless the content itself requires them
- Write in a terse, information-dense style — prefer "Hero HP: 8/14, stunned" over "The hero currently has
  8 hit points remaining out of a maximum of 14 and is affected by the stunned status condition"
- Organize by topic or entity, not chronologically
- If an entity has many attributes, list them compactly on one or two lines rather than one attribute per line
- A future AI agent will use this summary as its ONLY memory of everything that happened before — be complete\
"""


async def perform_compaction(
    *,
    repository: Repository,
    bifrost_client: BifrostClient,
    session_id: str,
    model_config: SessionModelConfig,
    current_job_id: str | None = None,
    live_event_bus: LiveEventBus | None = None,
) -> CompactionRecord:
    """Summarize the session's message history and persist a CompactionRecord.

    If current_job_id is None, covers all completed jobs.
    """
    # Get the latest completed job id to mark as checkpoint
    covers_up_to_job_id = await repository.get_latest_completed_job_id(session_id)
    if covers_up_to_job_id is None:
        raise ValueError("No completed jobs to compact")

    # Reconstruct the full history to summarize
    # Use a sentinel job id that won't exist so we get ALL completed jobs
    if current_job_id is None:
        sentinel = "__compaction_sentinel__"
    else:
        sentinel = current_job_id

    prior_jobs = await repository.list_completed_jobs_for_replay(
        session_id,
        current_job_id=sentinel,
        after_job_id=None,  # Get everything (compaction covers it all)
    )

    # Also check for existing compaction record to include its summary
    existing_compaction = await repository.get_latest_compaction_record(session_id)

    summarization_messages: list[dict[str, Any]] = [
        {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
    ]

    if existing_compaction:
        summarization_messages.append(
            {
                "role": "system",
                "content": f"Previous summary:\n{existing_compaction.summary_text}",
            }
        )

    # Add all prior job events as the history to compress
    history_text_parts: list[str] = []
    for job in prior_jobs:
        if job.prompt:
            history_text_parts.append(f"USER: {job.prompt}")
        for event in sorted(job.events, key=lambda e: e.id):
            if event.event_type == "model_output":
                history_text_parts.append(
                    f"ASSISTANT: {event.payload_json.get('text', '')}"
                )
            elif event.event_type == "tool_call":
                p = event.payload_json
                history_text_parts.append(
                    f"TOOL CALL: {p.get('exposed_tool_name')}({p.get('arguments', {})})"
                )
            elif event.event_type == "tool_result":
                p = event.payload_json
                history_text_parts.append(
                    f"TOOL RESULT: {p.get('exposed_tool_name')} -> {p.get('result', {})}"
                )

    if not history_text_parts:
        raise ValueError("No history content to compact")

    history_text = "\n".join(history_text_parts)
    summarization_messages.append(
        {
            "role": "user",
            "content": f"Please summarize this session history:\n\n{history_text}",
        }
    )

    logger.info(
        "Compacting session %s: summarizing %d jobs (covers_up_to=%s)",
        session_id,
        len(prior_jobs),
        covers_up_to_job_id,
    )

    response = await bifrost_client.chat_completion(
        model_config.provider_id,
        model_config.model_name,
        summarization_messages,
        [],  # no tools during compaction
        model_config.gateway_options,
        model_config.provider_options,
    )

    summary_text = response.content or ""
    summary_tokens = extract_tokens_from_response(response.raw)
    if summary_tokens is None:
        summary_tokens = count_tokens_for_text(summary_text)

    record = await repository.create_compaction_record(
        session_id,
        summary_text=summary_text,
        covers_up_to_job_id=covers_up_to_job_id,
        tokens_used=summary_tokens,
    )

    # Persist the summary as a visible chat event in the session transcript
    compaction_job_id = await repository.create_compaction_job(
        session_id,
        summary_text=summary_text,
        tokens_used=summary_tokens,
    )

    if live_event_bus is not None and current_job_id is not None:
        await live_event_bus.publish(
            current_job_id,
            "compaction",
            {
                "summary_text": summary_text,
                "tokens_used": summary_tokens,
                "covers_up_to_job_id": covers_up_to_job_id,
                "compaction_job_id": compaction_job_id,
            },
        )

    logger.info(
        "Compaction complete for session %s: record %s, summary_tokens=%d",
        session_id,
        record.id,
        summary_tokens,
    )
    return record
