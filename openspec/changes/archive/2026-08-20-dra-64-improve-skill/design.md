## Context

See [proposal.md](proposal.md) for motivation. The existing orchestrator skill keeps a compact
board summary but permits it to be updated from seat reports, keeps an open finding active through
later normal turns, and describes encounter resolution without a completion checkpoint. The player
skill correctly stops on an unverified action but does not distinguish a recovery-only finding turn
from an ordinary turn.

This change remains a runtime-skill-corpus change: the agent consumes Markdown instructions and
the services retain their current tool surface, finding store, and WebSocket behavior.

## Goals / Non-Goals

**Goals:**

- Make a verified `get_game_state` result the source of every prompt fact and persistent board
  summary fact.
- Define a finite reconciliation path: compare, take one fresh read, then abort with the last
  verified state if the disagreement remains.
- Make a finding lifecycle explicit: retain its returned identifier, dispatch only the concrete
  undo, verify it, resolve that identifier, and start normal play only with a prompt free of it.
- Make the encounter queue a completion gate rather than a narrative step.

**Non-Goals:**

- The skill does not add code-level state comparison, find new repair tools, or change a game
  service response.
- The orchestrator does not resolve a seat's undo or choose a player decision while handling an
  encounter.
- A successful state read is not assumed to validate hidden card identity; the skill only requires
  it to account for visible locations and known pending encounter work.

## Decisions

### Checkpointed, rather than report-derived, board facts

The orchestrator will take a delegated, compact state read before each player prompt and after a
phase-changing or scenario-changing action. It will use that checkpoint as the sole source for the
prompt's board and the round summary. Seat reports retain their role as an action audit and are
never promoted to facts merely because they are plausible.

Alternative considered: merge report facts into the summary until the next full read. Rejected
because an incorrect report is precisely the failure that makes the next seat act on a board that
does not exist. Alternative considered: read full state directly in the orchestrator. Rejected
because the existing context-budget rule delegates large state reads and keeps the returned shape
bounded.

### One retry defines a recoverable disagreement

When a checkpoint conflicts with the prior verified state on phase, visible relevant card location,
or a key total, the orchestrator makes one fresh delegated read. It may continue only when the read
establishes a single coherent state; otherwise it reports the conflict and aborts.

Alternative considered: keep retrying until values agree. Rejected because it can create an
unbounded game loop while hiding upstream DragnCards/WebSocket drift. Alternative considered: use
the newest value without comparison. Rejected because it treats a broken read as evidence and
produces contradictory player prompts.

### Finding handling is a recovery-only invocation keyed by `finding_id`

The orchestrator retains the identifier returned by `report_illegal_action`, includes only that
open finding in the owning seat's recovery prompt, verifies the undo from a checkpoint, then calls
`resolve_illegal_action` with the retained identifier. The recovery invocation ends after its
report; only a later prompt without the resolved finding authorizes ordinary play. The seat checks
its own finding list and reports the identifier and board observation if the finding remains.

Alternative considered: allow the seat to resume ordinary play after undoing the finding. Rejected
because the coordinator cannot verify and close the finding before new actions change the board.
Alternative considered: leave an open finding in every later prompt until an eventual check.
Rejected because stale findings bias agents toward passivity and make it impossible to tell recovery
from normal play.

### Encounter resolution has an explicit queue-to-checkpoint boundary

After dealing encounters, the orchestrator reveals and resolves each card in player order, delegates
only the choices belonging to a seat, then reads a checkpoint before ending the villain phase. A
visible facedown encounter card is acceptable only while it is explicitly pending in that queue;
after the checkpoint it is an abort condition unless the game state explains it as a deliberately
facedown object outside unresolved encounter work.

Alternative considered: treat `villain_encounter_phase` as sufficient evidence of completion.
Rejected because it deals cards but does not prove their reveal/effect sequence finished. Alternative
considered: make a player agent resolve the full encounter phase. Rejected because it violates the
existing authority boundary.

## Risks / Trade-offs

- [Additional state reads consume context and tool time] → Keep them delegated and request the
  compact existing board shape; checkpoints replace report-derived repairs rather than duplicating
  unbounded raw-state reads.
- [DragnCards can emit stale or delayed WebSocket state] → One fresh read distinguishes a transient
  update from persistent drift; persistent drift aborts rather than contaminating the record.
- [A conservative abort ends more games] → The final report preserves the last verified board and
  discrepancy, producing usable diagnostic evidence instead of an invalid evaluation run.
- [Recovery-only prompts cost a seat an invocation] → They prevent a verified undo and subsequent
  normal actions from being conflated, which is required for reliable finding closure.

## Migration Plan

1. Update the two skill Markdown files and the orchestrator reference files with the checkpoint,
   recovery, and encounter contracts.
2. Update the two main OpenSpec capability specs through the DRA-64 deltas at archive time.
3. Validate the OpenSpec change and lint the Markdown corpus. No service deployment, migration, or
   rollback is required; reverting the commit restores the previous skill text.

## Verification Notes

The change can be validated structurally by OpenSpec validation, repository linting, and reviewing
each delta scenario against the skill text. A live orchestrated game additionally requires the
shared DragnCards stack and an available player-model provider; without both, this change cannot be
proven through a real player turn or Playwright-driven session in this worktree.
