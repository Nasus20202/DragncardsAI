## Why

An orchestrated Marvel Champions game continued after contradictory board reads, incomplete
encounter handling, and a finding that had already been undone.  The resulting prompts made
players cautious rather than strategic, so the game was neither a reliable playthrough nor useful
evaluation evidence.  The runtime skill contract must make state verification and recovery gates
unambiguous before another turn is scheduled.

## What Changes

- Require the orchestrator skill to use verified game-state checkpoints as the source for player
  prompts and round summaries, and to abort rather than continue after an unresolved contradiction
  in phase, card location, or key board totals.
- Require an illegal-action finding to be tracked and resolved by its returned identifier after the
  owning seat's undo is observed; prohibit including a resolved finding in later normal-play prompts.
- Require the villain/encounter loop to reveal and resolve each dealt encounter card, with a
  checkpoint before phase progression.
- Teach player agents that an active finding blocks ordinary actions only until they perform its
  concrete undo, and that they must report an unresolvable board discrepancy instead of becoming
  passively conservative.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-orchestration`: Strengthen the orchestration skill contract for authoritative state,
  finding closure, encounter resolution, and abort conditions.
- `marvel-champions-play-skill`: Strengthen the single-hero skill's response to active findings and
  unreliable state.

## Impact

- Runtime skill corpus: `skills/marvel-champions-orchestrator/` and
  `skills/marvel-champions-play/`.
- OpenSpec contracts: `openspec/specs/game-orchestration/spec.md` and
  `openspec/specs/marvel-champions-play-skill/spec.md`.
- No service APIs, persistent data models, providers, dependencies, or infrastructure change.

## Non-goals

- Adding runtime enforcement, repair APIs, or a new board-state reconciliation service.
- Changing Marvel Champions rules, card data, seat ownership boundaries, or player strategy beyond
  recovery behavior.
- Retrofitting or grading the failed historical game described by DRA-64.
