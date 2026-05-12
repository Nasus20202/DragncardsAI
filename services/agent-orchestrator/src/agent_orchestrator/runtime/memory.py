"""Multi-turn message history builder.

Reconstructs the LLM messages list from prior job events for a session,
respecting any CompactionRecord checkpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent_orchestrator.storage.repository import Repository

logger = logging.getLogger(__name__)

# Event types to skip entirely during replay
_SKIP_TYPES = {"progress", "reasoning", "failure", "cancellation", "completion"}
_STATE_HEAVY_GAME_SERVICE_TOOLS = {
    "execute_action",
    "export_game_state_snapshot",
    "get_game_state",
    "load_game_state_snapshot",
    "reset_game",
    "set_player_count",
}


@dataclass(frozen=True)
class _ConversationMessage:
    order: int
    message: dict[str, Any]


@dataclass(frozen=True)
class _ToolExchange:
    order: int
    round_id: int
    assistant_content: str
    tool_call: dict[str, Any]
    tool_result: dict[str, Any]
    state_heavy: bool


@dataclass
class _PendingToolExchange:
    order: int
    tool_call_payload: dict[str, Any]
    tool_result_payload: dict[str, Any] | None = None


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
    replay_settings = await repository.get_session_replay_settings(session_id)

    messages: list[dict[str, Any]] = []
    conversation_messages: list[_ConversationMessage] = []
    tool_exchanges: list[_ToolExchange] = []
    next_order = 0

    if compaction:
        messages.append({"role": "system", "content": compaction.summary_text})
        logger.debug(
            "Replaying %d prior jobs after compaction checkpoint %s",
            len(prior_jobs),
            compaction.id,
        )
    else:
        logger.debug(
            "Replaying %d prior jobs (no compaction checkpoint)", len(prior_jobs)
        )

    for job in prior_jobs:
        job_conversations, job_exchanges, next_order = _reconstruct_job_replay_items(
            job, start_order=next_order
        )
        conversation_messages.extend(job_conversations)
        tool_exchanges.extend(job_exchanges)

    selected_message_orders = _select_recent_message_orders(
        conversation_messages,
        _normalize_replay_limit(
            None
            if replay_settings is None
            else replay_settings.context_recent_message_limit
        ),
    )
    selected_exchange_orders = _select_recent_tool_exchange_orders(
        tool_exchanges,
        _normalize_replay_limit(
            None
            if replay_settings is None
            else replay_settings.context_recent_tool_exchange_limit
        ),
    )
    messages.extend(
        _flatten_replay_items(
            conversation_messages,
            tool_exchanges,
            selected_message_orders,
            selected_exchange_orders,
        )
    )

    return messages


def _reconstruct_job_messages(job: Any) -> list[dict[str, Any]]:
    """Reconstruct the message sequence for a single completed job."""
    conversation_messages, tool_exchanges, _ = _reconstruct_job_replay_items(job)
    return _flatten_replay_items(
        conversation_messages,
        tool_exchanges,
        {message.order for message in conversation_messages},
        {exchange.order for exchange in tool_exchanges},
    )


def _reconstruct_job_replay_items(
    job: Any,
    *,
    start_order: int = 0,
) -> tuple[list[_ConversationMessage], list[_ToolExchange], int]:
    conversation_messages: list[_ConversationMessage] = []
    tool_exchanges: list[_ToolExchange] = []
    order = start_order

    if job.prompt_run:
        conversation_messages.append(
            _ConversationMessage(
                order=order,
                message={"role": "user", "content": job.prompt_run.prompt},
            )
        )
        order += 1

    sorted_events = sorted(job.events, key=lambda e: e.id)
    current_round_content: str | None = None
    current_round_exchanges: list[_PendingToolExchange] = []
    current_round_id = order

    def flush_current_round() -> None:
        nonlocal order, current_round_content, current_round_exchanges, current_round_id
        if current_round_content is None and not current_round_exchanges:
            return
        if not current_round_exchanges:
            conversation_messages.append(
                _ConversationMessage(
                    order=order,
                    message={
                        "role": "assistant",
                        "content": current_round_content or "",
                    },
                )
            )
            order += 1
        else:
            for exchange in current_round_exchanges:
                tool_call_payload = exchange.tool_call_payload
                tool_result_payload = exchange.tool_result_payload or {
                    "tool_call_id": tool_call_payload.get("tool_call_id", ""),
                    "result": {"is_error": True, "content": []},
                }
                tool_exchanges.append(
                    _ToolExchange(
                        order=order,
                        round_id=current_round_id,
                        assistant_content=current_round_content or "",
                        tool_call=_build_assistant_tool_call_message(tool_call_payload),
                        tool_result=_build_tool_result_message(tool_result_payload),
                        state_heavy=_is_state_heavy_tool_exchange(tool_call_payload),
                    )
                )
                order += 1
        current_round_content = None
        current_round_exchanges = []
        current_round_id = order

    for event in sorted_events:
        if event.event_type in _SKIP_TYPES:
            continue

        if event.event_type == "model_output":
            flush_current_round()
            current_round_content = event.payload_json.get("text", "")
            current_round_id = order
            continue

        if event.event_type == "tool_call":
            if current_round_content is None:
                current_round_content = ""
                current_round_id = order
            current_round_exchanges.append(
                _PendingToolExchange(
                    order=order,
                    tool_call_payload=event.payload_json,
                )
            )
            continue

        if event.event_type == "tool_result":
            payload = event.payload_json
            tool_call_id = payload.get("tool_call_id", "")
            for exchange in reversed(current_round_exchanges):
                if (
                    exchange.tool_call_payload.get("tool_call_id", "") == tool_call_id
                    and exchange.tool_result_payload is None
                ):
                    exchange.tool_result_payload = payload
                    break
            else:
                if current_round_content is None:
                    current_round_content = ""
                    current_round_id = order
                current_round_exchanges.append(
                    _PendingToolExchange(
                        order=order,
                        tool_call_payload={
                            "tool_call_id": tool_call_id,
                            "exposed_tool_name": payload.get("exposed_tool_name", ""),
                            "arguments": {},
                            "tool_name": payload.get("tool_name"),
                            "assignment": payload.get("assignment"),
                            "server_url": payload.get("server_url"),
                        },
                        tool_result_payload=payload,
                    )
                )

    flush_current_round()
    return conversation_messages, tool_exchanges, order


def _normalize_replay_limit(value: int | None) -> int | None:
    if value is None or value <= 0:
        return None
    return value


def _select_recent_message_orders(
    messages: list[_ConversationMessage],
    limit: int | None,
) -> set[int]:
    if limit is None:
        return {message.order for message in messages}
    return {message.order for message in messages[-limit:]}


def _select_recent_tool_exchange_orders(
    exchanges: list[_ToolExchange],
    limit: int | None,
) -> set[int]:
    if limit is None or len(exchanges) <= limit:
        return {exchange.order for exchange in exchanges}

    selected_orders: list[int] = []
    newest_state_heavy = next(
        (exchange.order for exchange in reversed(exchanges) if exchange.state_heavy),
        None,
    )
    if newest_state_heavy is not None:
        selected_orders.append(newest_state_heavy)
        if len(selected_orders) >= limit:
            return set(selected_orders)

    for exchange in reversed(exchanges):
        if exchange.order in selected_orders or exchange.state_heavy:
            continue
        selected_orders.append(exchange.order)
        if len(selected_orders) >= limit:
            return set(selected_orders)

    for exchange in reversed(exchanges):
        if exchange.order in selected_orders:
            continue
        selected_orders.append(exchange.order)
        if len(selected_orders) >= limit:
            return set(selected_orders)

    return set(selected_orders)


def _flatten_replay_items(
    conversation_messages: list[_ConversationMessage],
    tool_exchanges: list[_ToolExchange],
    selected_message_orders: set[int],
    selected_exchange_orders: set[int],
) -> list[dict[str, Any]]:
    first_selected_exchange_by_round: dict[int, int] = {}
    for exchange in tool_exchanges:
        if exchange.order not in selected_exchange_orders:
            continue
        first_selected_exchange_by_round.setdefault(exchange.round_id, exchange.order)

    timeline: list[tuple[int, str, Any]] = []
    for message in conversation_messages:
        if message.order in selected_message_orders:
            timeline.append((message.order, "conversation", message))
    for exchange in tool_exchanges:
        if exchange.order in selected_exchange_orders:
            timeline.append((exchange.order, "tool_exchange", exchange))
    timeline.sort(key=lambda item: item[0])

    messages: list[dict[str, Any]] = []
    for _, item_type, item in timeline:
        if item_type == "conversation":
            messages.append(item.message)
            continue

        assert isinstance(item, _ToolExchange)
        assistant_content = (
            item.assistant_content
            if first_selected_exchange_by_round.get(item.round_id) == item.order
            else ""
        )
        messages.append(
            {
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [item.tool_call],
            }
        )
        messages.append(item.tool_result)
    return messages


def _build_assistant_tool_call_message(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("tool_call_id", ""),
        "type": "function",
        "function": {
            "name": payload.get("exposed_tool_name", ""),
            "arguments": json.dumps(payload.get("arguments", {})),
        },
    }


def _build_tool_result_message(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": payload.get("tool_call_id", ""),
        "content": json.dumps(payload.get("result", {})),
    }


def _is_state_heavy_tool_exchange(payload: dict[str, Any]) -> bool:
    if payload.get("assignment") != "game-service":
        return False
    tool_name = payload.get("tool_name") or payload.get("exposed_tool_name") or ""
    return tool_name in _STATE_HEAVY_GAME_SERVICE_TOOLS
