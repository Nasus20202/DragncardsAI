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
You are compressing a Marvel Champions card game session history to free up context window space.

Produce a concise but complete game state summary. You MUST preserve ALL of the following:
- Hero identity, current HP, max HP, and any status effects (confused, stunned, etc.)
- Villain name, current HP, max HP, and current stage
- Current threat level on each scheme and the scheme's threat threshold
- ALL cards currently in play (hero board and encounter area), including attachments and tokens
- Encounter deck status (approximate size, any face-up encounter cards)
- What happened in the most recently completed turn and the result
- Any toughness tokens, damage tokens, or other game markers in play

Do NOT include:
- Step-by-step reasoning or planning from prior turns
- Verbose tool call traces or intermediate game states that have since changed
- Repetitive status updates

Output plain text only. Be concise. A future AI agent will use this summary as its only memory of what happened before.\
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
            "content": f"Please summarize this game history:\n\n{history_text}",
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
