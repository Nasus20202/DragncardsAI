"""Multi-turn message history builder.

Reconstructs the LLM messages list from prior job events for a session,
respecting any CompactionRecord checkpoint.
"""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_orchestrator.storage.repository import Repository

logger = logging.getLogger(__name__)

# Event types that we replay into the messages list
_REPLAY_TYPES = {"model_output", "tool_call", "tool_result"}
# Event types to skip entirely during replay
_SKIP_TYPES = {"progress", "reasoning", "failure", "cancellation", "completion"}


async def build_message_history(
    repository: Repository,
    session_id: str,
    current_job_id: str,
) -> list[dict[str, Any]]:
    """Return prior-turn messages to prepend before the current user prompt.

    If a CompactionRecord exists, returns [summary_message] followed by events
    from jobs created after covers_up_to_job_id.  Otherwise returns all prior
    job events in order.

    Does NOT include the current job's prompt — caller appends that.
    """
    compaction = await repository.get_latest_compaction_record(session_id)

    # Fetch completed prior jobs in chronological order (excluding current job)
    prior_jobs = await repository.list_completed_jobs_for_replay(
        session_id,
        current_job_id=current_job_id,
        after_job_id=compaction.covers_up_to_job_id if compaction else None,
    )

    messages: list[dict[str, Any]] = []

    if compaction:
        messages.append({"role": "system", "content": compaction.summary_text})
        logger.debug(
            "Replaying %d prior jobs after compaction checkpoint %s",
            len(prior_jobs),
            compaction.id,
        )
    else:
        logger.debug("Replaying %d prior jobs (no compaction checkpoint)", len(prior_jobs))

    for job in prior_jobs:
        job_messages = _reconstruct_job_messages(job)
        messages.extend(job_messages)

    return messages


def _reconstruct_job_messages(job: Any) -> list[dict[str, Any]]:
    """Reconstruct the message sequence for a single completed job."""
    messages: list[dict[str, Any]] = []

    # User turn
    if job.prompt_run:
        messages.append({"role": "user", "content": job.prompt_run.prompt})

    # Rebuild assistant + tool rounds from events
    sorted_events = sorted(job.events, key=lambda e: e.id)

    # Collect model_output and tool_call/tool_result events into assistant rounds
    current_assistant: dict[str, Any] | None = None

    for event in sorted_events:
        if event.event_type in _SKIP_TYPES:
            continue

        if event.event_type == "model_output":
            # Flush previous assistant message if any
            if current_assistant is not None:
                messages.append(current_assistant)
            current_assistant = {
                "role": "assistant",
                "content": event.payload_json.get("text", ""),
                "tool_calls": [],
            }

        elif event.event_type == "tool_call":
            if current_assistant is None:
                # Shouldn't happen, but handle gracefully
                current_assistant = {"role": "assistant", "content": "", "tool_calls": []}
            payload = event.payload_json
            current_assistant["tool_calls"].append(
                {
                    "id": payload.get("tool_call_id", ""),
                    "type": "function",
                    "function": {
                        "name": payload.get("exposed_tool_name", ""),
                        "arguments": json.dumps(payload.get("arguments", {})),
                    },
                }
            )

        elif event.event_type == "tool_result":
            # Flush pending assistant message before tool result
            if current_assistant is not None:
                messages.append(current_assistant)
                current_assistant = None
            payload = event.payload_json
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": payload.get("tool_call_id", ""),
                    "content": json.dumps(payload.get("result", {})),
                }
            )

    # Flush any remaining assistant message
    if current_assistant is not None:
        # Strip empty tool_calls list to keep messages clean
        if not current_assistant["tool_calls"]:
            del current_assistant["tool_calls"]
        messages.append(current_assistant)

    return messages
