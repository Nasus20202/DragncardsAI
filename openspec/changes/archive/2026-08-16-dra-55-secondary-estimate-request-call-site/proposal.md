# Continuation guard: move onto `estimate_request`

## Why

DRA-45's design.md (`openspec/changes/archive/2026-08-05-dra-45-auto-continue-truncated-turns/design.md` lines 181-187) documented that after the DRA-33 rebase, the continuation guard should move onto `estimate_request` so there is one call site rather than two summations. The numbers do not change, only where they are added up.

The intent was to align the continuation guard with the rest of the token accounting in the worker, which already uses `estimate_request` for the per-call budget check at `prompt_run.py:1276` and the transcript metadata at `session_transcript.py:201`. The guard is the only token-sum-at-a-request site that still adds the two primitives directly.

DRA-55's "Secondary item found at merge time" is the same observation: the archived design describes an intention the code does not follow, and the call-site tidiness is worth closing so the description stops describing a state the code does not have.

## What Changes

- **`services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py:1157`** — replace the two-summation form
  ```python
  estimate = estimate_tokens_for_messages(candidate) + estimate_tokens_for_tools(tools)
  ```
  with the call to `estimate_request`:
  ```python
  estimate = estimate_request(
      system_prompt="",
      tools=tools,
      replay_messages=candidate,
      context_window_size=context_window_size,
  ).total
  ```
  The `candidate` list built just above (`[*messages]` plus the assistant partial content and the continuation instruction) becomes the `replay_messages` argument; `tools` and `context_window_size` are the same variables already in scope.
- The numbers are identical. `estimate_request(system_prompt="", ...)` contributes zero for `system_prompt` (the empty string falls through the `if system_prompt` guard in `context_estimate.py:124-127`); `user_message` is absent and contributes zero (`context_estimate.py:130-134`); `replay` is `estimate_tokens_for_messages(candidate)`; `tools` is `estimate_tokens_for_tools(tools)`. The total is the same sum.
- The imports of `estimate_tokens_for_messages` and `estimate_tokens_for_tools` stay: they are still used elsewhere in the file (`:497`, `:1289`, `:1395`, and via the `compactable_replay` path).

### Modified Capabilities

- **`agent-orchestrator`** — the requirement "An automatic continuation never sends an over-window request" (`openspec/specs/agent-orchestrator/spec.md` lines 2480-2512) remains satisfied. The implementation uses the same `estimate_request` helper the rest of the worker uses; the wording of the requirement is about the estimate being taken, not about which helper produces it.

### Impact

- **agent-orchestrator** — `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py` (one site, three lines).
- **No spec changes.** The behaviour is byte-identical and the spec already documents the intent.
- **No test changes.** The existing `tests/unit/test_truncated_turn_continuation.py` covers the guard's behaviour; the refactor is a call-site change.
- **No new dependencies.** `estimate_request` is already imported at `prompt_run.py:20`.

## Non-goals

- **No behaviour change.** The numbers are byte-identical.
- **No new tests.** The shared `estimate_request` is already covered indirectly; the site-specific coverage already exists.
- **No other call-site changes.** The three other sites that still sum primitives (`prompt_run.py:497`, `:1289`, `:1395`) measure a single component rather than a request, and the DRA-45 design note scoped the refactor to the continuation guard specifically.
- **No spec re-text.** The existing requirement is about the estimate, not the helper.
