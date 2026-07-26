# Hierarchical per-player evaluation (moves → rounds → games)

## Why

Today evaluations are flat: a move, a round, a seq range, or a whole game is graded as a
single verdict, and round/game scope grades the period in aggregate without requiring its
moves to be graded and without distinguishing players. Users want a hierarchy where a round's
score is grounded in its (already-graded) moves and a game's score in its (already-graded)
rounds, and where each player in a multiplayer game gets a **separate** result so their play
can be compared.

## What Changes

Three evaluation **levels** with a dependency relationship: **move → round → game**.

- **Auto-grade cascade.** A higher-level evaluation requires every component beneath it to be
  graded. Requesting a round (or game) evaluation first grades any ungraded moves (then rounds),
  then evaluates the requested level — one request fans out across the whole subtree it needs.
- **Judge with child context.** A round/game score is NOT a numeric average: the judge grades
  the round/game holistically, given the child verdicts (scores + rationales) as context, so
  cross-move/cross-round strategy is captured. The roll-up still *requires* the children graded.
- **Per-player results.** Each move is attributed to the **active player** derived from the game
  state at that move (turn/step + firstPlayer). A round/game evaluation produces a **separate
  verdict per player** who acted in that span — scoring that player's moves (round) or that
  player's rounds (game) — so each player has their own move/round/game scores and they can be
  compared side by side. Move verdicts are inherently attributed to their acting player.
- **Player on the verdict.** Evaluation events/verdicts gain a `player` attribute (player id,
  e.g. `player1`) alongside `scope`/`target_seq`/`round_span`. Single-player games simply have
  one player (`player1`).
- **UI.** The dashboard can request a full cascade evaluation (e.g. "evaluate whole game →
  grades everything"); shows per-player scores at each level; and presents a per-player
  game scorecard (move/round/game scores per player) so players can be compared.

## Impact

- Affected specs: `agent-move-evaluation` (levels, dependency/cascade, per-player verdicts,
  player attribution, hierarchical judging), `history-event-store` (evaluation envelope `player`
  field), `game-history-ui` (per-player score display + cascade request + scorecard).
- Affected code:
  - `services/eval-service/` — player-attribution from game_state, hierarchical target expansion
    + dependency gating + cascade orchestration, per-player round/game judging with child-verdict
    context, verdict `player` field, schemas, repository, worker.
  - `services/history-service/` — evaluation envelope/schema accepts `player`.
  - `services/dashboard/` — request cascade eval, per-player score chips in the transcript
    verdict sub-tree, a per-player game scorecard, queue rows reflecting cascade progress.
- Builds on `eval-queue` (queue shows the cascade's many sub-evaluations) and the existing
  scope model. No change to how moves/states are recorded by game-service.
- Constraint: per-player attribution and roll-up are derived from recorded history (game_state +
  move + child verdicts); no in-memory state.

## Open considerations (resolved)

- Roll-up = judge-with-child-context (not numeric average).
- Prerequisites = auto-grade missing children first (cascade), not block.
- Player attribution = active player from game state at the move.
