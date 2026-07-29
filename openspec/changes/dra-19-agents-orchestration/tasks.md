# Tasks

Ordered so that each numbered section is independently shippable and nothing in it
alters the chat flow. Sections 1–4 are the vertical slice delivered first; sections
5–8 build on it and are explicitly staged after, because the mode flag is what gates
them and it has to exist before any of them can be reached.

## 1. Confirm the existing paths before changing them

- [x] 1.1 Confirm `_launch_child_agent` is the single place `multi_turn_memory=False`
      is set, and that no API path creates a child with memory on.
- [x] 1.2 Confirm `PromptRunService._maybe_terminate_child_session` is what makes a
      child disposable, and that it is reached from the child's own run.
- [x] 1.3 Confirm `multi_turn_memory` toggles exactly two things — auto-compaction
      and prior-turn replay — so enabling it on a seat needs no other change.
- [x] 1.4 Confirm the orchestrator's system prompt is assembled only from static
      text, the skill registry, and the persona catalogue, so no player-authored
      text can reach it today.
- [x] 1.5 Confirm migrations are hand-numbered dual-dialect raw SQL discovered from
      the directory with no registry to edit, and that the next free number is
      `0011` (`0010_job_questions` is the highest present).
- [x] 1.6 Confirm the DRA-16 dashboard persona-picker touchpoints, so the mode
      control follows the same seven-file path rather than a new one.

## 2. Session mode

- [x] 2.1 Add migration `0011_session_mode_and_player_sessions` in both dialects:
      `agent_sessions.session_mode VARCHAR(16) NOT NULL DEFAULT 'chat'`,
      `session_player_configs.persona VARCHAR(64)`,
      `session_player_configs.agent_session_id VARCHAR(36)`.
- [x] 2.2 Add `session_mode` to the `AgentSession` model with the `chat` default.
- [x] 2.3 Add the mode to `SessionCreateRequest`, `SessionUpdateRequest`, and
      `SessionSummary`, constrained to the two literal values so an unknown mode is
      a validation error.
- [x] 2.4 Accept the mode in `create_session` and add `update_session_mode`, which
      refuses when the session already has a job.
- [x] 2.5 Return 409 from `PATCH /sessions/{id}` when the mode change is refused,
      and 400 for an unknown mode.
- [x] 2.6 Unit tests: the default, creation in orchestrated mode, the change before
      the first job, the 409 after it, and the rejection of an unknown mode.
- [x] 2.7 Verify the migration on real PostgreSQL through the integration suite, and
      unit-test that a session created without a mode reads back as `chat`.

## 3. Stateful per-seat player sessions

- [x] 3.1 Add `persona` and `agent_session_id` to the `SessionPlayerConfig` model and
      to `ResolvedPlayerAgentConfig`/`as_summary`.
- [x] 3.2 Add `set_player_agent_session` to the players repository so a seat's session
      id is recorded once, and expose both new fields through
      `PlayerConfigRequest`/`PlayerConfigResponse`.
- [x] 3.3 Validate a named persona when a seat is configured, rejecting an unknown
      one as a bad request.
- [x] 3.4 Give `_launch_child_agent` an explicit `multi_turn_memory` argument
      instead of the hard-coded `False`, defaulting to `False` so every existing
      caller is unchanged.
- [x] 3.5 In `prompt_player_agent`, branch on the session's mode: in `chat` keep
      today's memoryless spawn; in `orchestrated` create the seat's session with
      memory on and record its id, or reuse the recorded one.
- [x] 3.6 Apply the seat's persona snapshot when the seat's session is created,
      through the same `as_snapshot` path `spawn_subagent` uses.
- [x] 3.7 Guard `_maybe_terminate_child_session` so a seat session is not terminated
      when one of its jobs ends.
- [x] 3.8 Terminate a seat's session when the seat's configuration is deleted and
      when the orchestrating session is terminated, and delete a seat's session when
      the orchestrating session is deleted — a seat session is a separate row, so
      neither cascades on its own.
- [x] 3.9 Unit tests: first prompt creates and records, second prompt reuses, a chat
      session still spawns memoryless, a seat session survives its job, and the
      seat's persona is snapshotted once.

## 4. The player-report envelope

- [x] 4.1 Add `wrap_player_report` building the server-side envelope: seat id and job
      status as fields, the seat's text in one delimited block, and the fixed
      data-not-instruction note.
- [x] 4.2 Strip the delimiters from the seat's text before wrapping.
- [x] 4.3 Use the envelope for the report a seat's completion returns to the
      orchestrator in orchestrated mode.
- [x] 4.4 Unit tests: the envelope shape, a report claiming another seat's id, a
      report containing the closing delimiter, and the assertion that an
      injection-shaped report does not appear in the orchestrator's assembled
      system prompt.

## 5. The seat guard

- [ ] 5.1 Add `runtime/seat_guard.py` with a pure function from
      (caller seat, tool name, arguments) to a violation or `None`, recognising a
      seat identifier value, a `player<N><Group>` group id, and an explicit
      player-identifying argument.
- [ ] 5.2 Leave non-seat-owned groups unrestricted, and document why in the module.
- [ ] 5.3 Apply the guard in the tool-dispatch path for jobs whose session is a
      seat, before the tool is invoked.
- [ ] 5.4 Return an error result naming the argument and the foreign seat, and record
      a `seat_scope_violation` event on the job.
- [ ] 5.5 Register `seat_scope_violation` in the dashboard's `STREAM_EVENT_TYPES`.
- [ ] 5.6 Unit tests: a foreign group refused, an own group allowed, a shared group
      allowed, an explicit foreign seat argument refused, and the orchestrator not
      being guarded.

## 6. Player-to-player messaging

- [ ] 6.1 Add the `player_messages` table to migration `0012` in both dialects, with
      sender, recipient, orchestrating session, body, and delivery timestamps.
- [ ] 6.2 Add a `PlayerChannelRepositoryMixin` with send, list-undelivered, and a
      conditional mark-delivered.
- [ ] 6.3 Add the `send_player_message` built-in, registered only for a seat job of an
      orchestrated session, refusing a recipient that is not a configured seat of the
      same orchestrating session and refusing the sender itself.
- [ ] 6.4 Deliver undelivered messages at the start of a seat's invocation, wrapped as
      data attributed to the sending seat, and mark them delivered.
- [ ] 6.5 Unit tests: a message stored, the tool absent for the orchestrator and in
      chat mode, an unconfigured recipient refused, and delivery happening exactly
      once.

## 7. Illegal-action findings

- [ ] 7.1 Add the `player_illegal_actions` table to migration `0012` in both dialects.
- [ ] 7.2 Add repository methods to open, list-open-for-seat, and conditionally resolve
      a finding.
- [ ] 7.3 Add `report_illegal_action` and `resolve_illegal_action` built-ins gated to
      the orchestrating job, and a read-only view of its own findings for a seat.
- [ ] 7.4 Carry every open finding into each invocation of the seat it concerns, as
      data naming the violation and the required undo.
- [ ] 7.5 Unit tests: opening a finding, an open finding appearing in two consecutive
      invocations, a seat's attempt to resolve refused, and a resolved finding no
      longer appearing.

## 8. Dashboard, evaluation, history, and documentation

- [x] 8.1 Add the mode to `SessionSummary` and `SessionDraft` in the dashboard's
      types, to `createSession`/`updateSession`, to `createDefaultDraft` and
      `draftFromSession`, and tolerate its absence in a stored draft.
- [x] 8.2 Add the session-mode control as a new component in the config panel,
      disabled with a reason on a session that has run a job.
- [x] 8.3 Dashboard unit tests: the default, the value sent on create, the disabled
      state, and an older stored draft loading.
- [ ] 8.4 Add the seat roster with per-seat persona and model editing.
- [ ] 8.5 Link each prompted seat to its own session transcript, and show "no context
      yet" for a seat that has not played.
- [ ] 8.6 Render the seat-scope refusal and the illegal-action finding in the
      transcript.
- [ ] 8.7 Carry the session mode and the seat id on emitted history events, and read
      the mode back in the history projection.
- [ ] 8.8 State the mode in eval-service's judge projection and include the round's
      illegal-action findings as evidence.
- [x] 8.9 Update `services/agent-orchestrator/README.md` (session mode, the seat
      lifecycle) and `services/agent-orchestrator/AGENTS.md` (a Session Modes and
      Player Seats section stating the trust-boundary rules a future change must
      not break).
- [ ] 8.10 Update the root `README.md` with the mode choice at session creation.

## Deferred, and why

Sections 5 through 7, and tasks 8.4 through 8.8 and 8.10, are specified here in full
and are **not** implemented by the first pass of this change. The reason is scope
rather than uncertainty: the mode flag, the stateful seat, and the report envelope are
the load-bearing parts — the first is what every other behaviour is gated on, the
second is the part the issue calls out as missing, and the third is the part of the
trust boundary that is wrong to leave half-built. The seat guard, the messaging
channel, and the findings store each need their own migration, tool registration, and
test surface, and shipping any of them partially would mean a boundary that looks
enforced and is not — which is worse than one that is honestly absent.

Nothing deferred here is blocked by anything: each remaining section is additive
behind the mode flag, and the specs above state the required behaviour precisely
enough to implement without re-deciding anything.
