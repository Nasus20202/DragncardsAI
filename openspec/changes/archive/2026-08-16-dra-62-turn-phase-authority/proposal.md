# Enforce turn and phase authority after the fact, as recorded findings

## Why

DRA-57 documented the turn-and-phase rule in the skill files: a seat must not
advance the phase and must not play out of turn. Documentation is not
enforcement, and the reason it stopped at documentation is written in the seat
guard's own opening lines (`runtime/seat_guard.py:62-65`):

> It does not police turn or phase authority. *When* an action happens — that a
> seat must not advance the phase or play out of turn — is an orchestrator-side
> judgement made from game state, not a property of the arguments. This function
> answers only "whose cards does this call touch".

That is correct as a scoping decision: `check_seat_scope` is a pure function over
tool arguments, and turn order is not visible there. But the orchestrator-side
judgement the note defers to does not exist. A repository-wide search for
`turn_order`, `current_turn`, `active_player`, `phase_guard` and "out of turn"
across `services/agent-orchestrator/src/` returns exactly one hit: the docstring
above, describing the check as somebody else's job. The `game-orchestration`
spec has the same shape — "the orchestrator SHALL treat a seat's attempt to
advance the game as an illegal action to be reported" — with no mechanism that
makes the report happen. So a seat that calls `next_step` during the villain
phase, or plays cards while the villain resolves, is recorded on the timeline as
a move like any other: nothing distinguishes it, and the judge grades it as a
legal play.

Three options were considered:

1. **A turn-authority check in the tool-call path that reads game state before
   dispatching.** Most thorough, and the most expensive: it needs a state read to
   gate *every* tool call from a seat, plus refusal plumbing parallel to the seat
   guard. It also leaves games already recorded unrepairable — the violation was
   never recorded, so there is nothing to evaluate retroactively.
2. **Withhold the phase tools from seat personas by default.** Cheap, but it only
   hides the four phase-advancing tools; it does nothing about action tools
   played during the villain phase, and it is a configuration change that an
   operator can undo, not an enforcement. It also silently changes the tool
   surface every seat sees, which is a much wider behavioural change than the
   defect being fixed.
3. **Detect after the fact and record a finding, reusing DRA-30's
   illegal-action findings store.** The cheapest credible option: no state read
   on the common path, no new refusal surface, and it writes the evidence the
   judge is already fed — `HistoryEventEmitter.emit_illegal_action` publishes a
   finding as an `illegal_action` history event that eval-service hands the judge
   as recorded evidence, never as a move. That repairs the evaluation blind spot
   for games already recorded, because the finding lands on the same timeline the
   judge reads.

The orchestrator's pick is option 3. It does not refuse the call — the seat
guard's answer to "whose cards" is still the only pre-dispatch gate — but a seat
that advances the phase or acts outside the player phase gets an open finding
against it, which is carried into every later invocation of that seat until the
coordinator resolves it, and which the judge sees as evidence.

## What Changes

### The rule, and what state it is read from

A new pure module `runtime/seat_turn_guard.py` (mirroring `seat_guard.py`:
no repository, no I/O) classifies the current phase from the simplified game
state's `stepId` and answers one question per call:

- `next_step`, `prev_step`, `player_end_phase`, `villain_end_phase` — the
  **phase-advancing tools**. A seat may call them only while the board is in the
  player phase (steps `1.1`, `1.2`). Called anywhere else — beginning of round,
  villain phase, end of round — the call advances the game when no seat holds the
  authority to do so.
- The **seat action tools** (move/draw/exhaust/ready/flip/set/modify/zero
  tokens, shuffle, discard minion/side scheme, encounter automation, and the
  like). A seat may use them only during the player phase. Called while the
  villain phase resolves, the seat is acting out of turn.

The boundary is stated plainly: *which seat* holds the turn within the player
phase is not a field anywhere in the game state — `stepId` gives the phase, not
the acting player (root `AGENTS.md`, "Fetch the live board state") — so the
within-player-phase slice of turn order stays the orchestrator's prompt-tracked
judgement. This change enforces what game state can prove: that a seat's call is
in a phase that grants no seat authority. That is also exactly the gap the
orchestrator previously had to notice by hand.

`mulligan_draw_hand` is deliberately not an action tool for this rule: it is the
one action a seat performs during setup (round 0, outside the player phase), so
flagging it would turn every game's opening into a finding.

### The detection, at the call site

`PromptRunService.run`'s tool-call loop already resolves the seat identity and
runs `check_seat_scope` ahead of both dispatch paths. The turn-authority check
sits beside it, after the seat-scope refusal and before dispatch:

1. Skip unless the caller is a seat (`seat_identity is not None`) and the tool
   is a game-service tool in one of the two sets — the common path (read-only
   tools, builtins, lifecycle tools) never touches game state.
2. Resolve the game id with the mechanism the session already uses
   (`_session_game_id` — `metadata.game_id`, the same key the seat's child
   session inherits at creation). No game attached means nothing to read and
   nothing to judge.
3. Read the current step through the existing game-service state read: the
   session's own tool catalog holds the `get_game_state` definition, and
   `McpToolCatalog.call_tool(..., ignore_failures=True)` calls it with the game
   id. The read is best-effort — an unreachable game-service means no finding,
   never a failed job.
4. `check_turn_authority` decides. On a violation, record a finding through the
   DRA-30 store exactly as the `report_illegal_action` built-in does:
   `repository.open_illegal_action` on the orchestrating session, then
   `_announce_illegal_action_finding` — the durable `job_events` row, the live
   bus copy under the durable id, and the `illegal_action` history event for the
   judge. The announcement goes to the orchestrating job (the seat's
   `parent_job_id`), which is the stream the coordinator reads.

The call is then dispatched normally. Detection after the fact is the point of
option 3: the finding is recorded, the play is not blocked.

### The scope note, updated in place

`seat_guard.py:62-65` is the existing scope decision this change aligns with. Its
"does not cover" bullet is rewritten to name the new module as the enforcement of
the orchestrator-side judgement it defers to, so the two modules read as one
story: the seat guard answers *whose* cards, the turn guard answers *when*.

### Tests

- Pure-rule tests for `check_turn_authority`: the three ticket scenarios (a seat
  calling `next_step` during the villain phase, `player_end_phase` out of turn,
  an action tool during the villain phase), the negatives (player-phase action
  tool, read-only tool during the villain phase, unknown/missing step id), and
  the tool-set boundary (mulligan, lifecycle, and read-only tools never fire).
- Wiring tests through the real `PromptRunService`, mirroring the seat-guard
  tests in `tests/unit/test_prompt_run.py`: a seat job whose model calls
  `next_step` with the board in the villain phase produces an open finding in the
  store, a live `illegal_action_finding` event, and an `illegal_action` history
  emission; the orchestrating job is not checked; a read-only call during the
  villain phase records nothing.

### Modified Capabilities

- `game-orchestration` — the turn-and-phase half of the
  orchestrator/player separation is now enforced server-side after the fact: a
  seat that advances the phase or acts outside the player phase gets a recorded
  illegal-action finding, instead of the report being the orchestrator's to
  remember to make.

### Impact

- **A seat that misbehaves accumulates open findings**, each carried into every
  later invocation of that seat until resolved. This is the DRA-30 store's
  existing contract; the automatic detector writes to it the same way the
  `report_illegal_action` tool does, and resolution stays a coordinator
  judgement verified against game state — a seat cannot close one itself.
- **The state read happens only for phase-sensitive game-service calls from a
  seat** (the four phase tools plus the action-tool set), not per tool call, and
  it degrades silently when game-service is unreachable.
- **No new event type**: the detection reuses `illegal_action_finding`, so the
  dashboard's `STREAM_EVENT_TYPES` and the job-event stream need no change.
- **No new configuration, no migration, no new service surface.**
