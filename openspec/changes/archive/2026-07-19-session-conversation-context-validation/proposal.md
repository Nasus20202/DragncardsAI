# Validate the restore conversation context

## Why

`POST /sessions/restore` accepts a `conversation_context` typed only as
`list[dict[str, Any]]` with no size, shape, or type constraints. The supplied
context is persisted verbatim into the session's `metadata_json` and, on the
session's next turn, deep-copied straight into the prompt's message list and sent
to the LLM. Malformed input therefore reaches the runtime unchecked:

- An unbounded number of messages or an unbounded total size can bloat the
  session metadata row and blow the model context window.
- Messages of arbitrary shape (missing or non-string `role`, or a `role` outside
  the chat-message contract) flow directly into the OpenAI-shaped message list,
  which can break the downstream chat completion request.

The orchestrator itself only ever produces messages with a `role` of `system`,
`user`, `assistant`, or `tool` (the exact shape the history-service captures and
hands back on restore), so the request can be validated to that same contract.

## What Changes

- **agent-orchestrator (restore request validation)** — `SessionRestoreRequest`
  SHALL validate `conversation_context` before it reaches the runtime: reject a
  context with more than a bounded number of messages, reject any message that is
  not an object or whose `role` is not one of `system`, `user`, `assistant`, or
  `tool`, and reject a context whose serialized size exceeds a bounded byte
  limit. `game_id` SHALL also be length-bounded consistently with the
  history-service `game_id` contract. A malformed request SHALL be rejected with
  a validation error before any persistence or session mutation.

## Impact

- Affected specs: `agent-orchestrator` (Resume a session from a supplied
  conversation context — input validation).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/schemas/sessions.py`
  (bounds + per-message shape/role validation on `SessionRestoreRequest`).
- No change to the well-formed restore flow; only malformed input is now
  rejected. No database or API-shape changes.
