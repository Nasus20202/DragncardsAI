# Tasks

## 1. Establish what a tool event actually contains

- [x] 1.1 Confirm the `tool_call` payload the orchestrator records
      (`tool_call_id`, `exposed_tool_name`, `tool_name`, `assignment`,
      `server_url`, `arguments`) and the `tool_result` payload (the same keys plus
      `is_error` and `result`), in `runtime/prompt_run.py`.
- [x] 1.2 Confirm the full set of system tools in
      `runtime/builtin_tools.py`: `load_skill`, `load_skill_reference`,
      `spawn_subagent`, `wait_for_subagent`, `list_player_agents`,
      `prompt_player_agent`, and what each one returns.
- [x] 1.3 Confirm `list_player_agents` needs no bespoke card: it takes no
      arguments and returns a small JSON roster, which the generic card
      pretty-prints adequately.
- [x] 1.4 Re-read DRA-8's archived change so the per-update containment it
      established is preserved rather than rediscovered.
- [x] 1.5 Confirm the subagent output modal that already exists is what a "view
      the subagent" affordance should open, and that DRA-21 owns improving it.

## 2. Pair a call with its result

- [x] 2.1 Replace the `tool_call` / `tool_result` `AggEvent` kinds with one
      `tool_exchange` carrying both events, pairing by `tool_call_id`.
- [x] 2.2 Keep an unpaired result renderable, and keep the unknown-event-type
      fallback working.
- [x] 2.3 Keep the paired events' identities intact so the memoised card still
      bails out — the pairing indexes events, it does not copy them.

## 3. Bounded, redacted formatting

- [x] 3.1 Add `features/play/lib/tool-call-presentation.ts` with `redactSecrets`
      ported from the eval service's `error_detail.py` patterns.
- [x] 3.2 Add `stringifyBounded`, which pretty-prints JSON but stops at a
      character budget, and `boundedValueText`, which redacts inside a slack
      window and then caps, dropping the token the cut landed inside.
- [x] 3.3 Add `buildToolExchangeView`, producing the tool name, named arguments,
      status, one-line summary, result size and error preview without serialising
      any payload in full.
- [x] 3.4 Add the full-text escapes `toolValueText` / `toolResultText`, used only
      from an already-expanded body.
- [x] 3.5 Add `subagentReference`, reading the child job from a launch result or a
      wait's arguments.

## 4. The cards

- [x] 4.1 Add `features/play/components/tool-exchange-block.tsx` with the shared
      collapsible frame, reusing the transcript's existing card classes.
- [x] 4.2 Implement the generic card: name, argument summary, status, and an
      expanded body of named arguments, result, and provenance.
- [x] 4.3 Implement the subagent-launch card with the **View subagent** button and
      the seat for `prompt_player_agent`.
- [x] 4.4 Implement the subagent-wait card with the live spinner and `role="status"`
      announcement while pending.
- [x] 4.5 Implement the skill-load card.
- [x] 4.6 Add the name → presentation → renderer registry with the generic
      fallback.
- [x] 4.7 Deliver the view-subagent handler through a context so the memoised
      cards do not gain a prop, and pass a `useCallback`-stable handler from the
      Play workspace.

## 5. Tests

- [x] 5.1 Cover the redaction shapes, including prose that must not be mangled.
- [x] 5.2 Cover `stringifyBounded` stopping early on a 50 000-entry list and
      matching `JSON.stringify` on small values.
- [x] 5.3 Cover `boundedValueText` redacting a credential past the displayed
      window and dropping a straddling token.
- [x] 5.4 Cover the view: naming, summarising, pending/ok/error status, nested
      arguments summarised by shape, and the no-arguments fallback.
- [x] 5.5 Cover the registry mapping and its generic fallback.
- [x] 5.6 Render the generic card collapsed and expanded, and assert the result is
      absent until expanded.
- [x] 5.7 Render the bespoke cards: the launch button firing with the child job id,
      the seat on a player prompt, the wait spinner appearing and then being
      replaced by the outcome, and the skill name on the header.
- [x] 5.8 Large payloads: assert a collapsed card stays header-sized and never
      contains the payload, that an expanded one is capped and offers the rest,
      and — the DRA-8 guard — that a streamed token in one job rebuilds no settled
      tool card.

## 6. Security review follow-ups

- [x] 6.1 Redact an argument whose own *name* names a credential: the name and the
      value are rendered as separate text, so `redactSecrets` — which matches on
      the field name in front of a value — could never fire on it. Cover the
      summary, the expanded row, and the "show all" path.
- [x] 6.2 Redact `assignment` / `server_url` on the provenance line, and the tool
      name, the seat, the skill names and the subagent name on the headers. A
      registered MCP URL can carry a token in its query.
- [x] 6.3 Accept a `child_job_id` read out of a model-written argument only when it
      is shaped like a job id, so a value carrying path syntax cannot be turned
      into a request elsewhere by the view it opens.
- [x] 6.4 Add tests for all three.

## 7. Surrounding files

- [x] 7.1 Document the registry extension point in `services/dashboard/AGENTS.md`
      so the next person adding a system tool knows where to plug in.
- [x] 7.2 Confirm nothing infra-facing was made stale: no README describes
      transcript rendering, and the change adds no dependency, environment
      variable, port, container, script, make target or API surface.

## 8. Verification

- [x] 8.1 `./scripts/lint.sh --fix` clean.
- [x] 8.2 `pnpm typecheck` clean in `services/dashboard`.
- [x] 8.3 `./scripts/test.sh unit` passes; dashboard 355 → 399 tests.
- [x] 8.4 `openspec validate --all` reports the same pass count as before the
      change, the pre-existing `spec/typed-game-actions` failure aside.
- [x] 8.5 Sync `openspec/specs/dashboard/spec.md`.
