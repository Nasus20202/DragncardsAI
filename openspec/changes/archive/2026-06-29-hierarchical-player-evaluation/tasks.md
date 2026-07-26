## 1. eval-service — player attribution

- [x] 1.1 Helper to attribute each agent-move seq to the active player, derived from the game
      state at/around that move (`firstPlayer`, `playerData`/`numPlayers`, `stepId`/turn order).
      Single-player → `player1`. Expose attribution for a span (round/game) as the set of players
      who acted.
- [x] 1.2 Tests for attribution: single-player, multi-player turn alternation, encounter/shared steps.

## 2. eval-service — hierarchical levels + cascade

- [x] 2.1 Model the move→round→game dependency. A round target depends on its move targets; a game
      target depends on its round targets.
- [x] 2.2 Cascade orchestration: requesting round/game expands into the full subtree of required
      targets (ungraded moves first, then rounds, then the requested level), respecting config-aware
      idempotency (don't re-grade already-graded, unforced children).
- [x] 2.3 Per-player target expansion: a round/game request creates one target per player who acted
      in the span (plus the underlying per-move targets, which are inherently per acting player).
- [x] 2.4 Tests: game request fans out to moves→rounds→game; already-graded children are reused;
      per-player targets created for a multi-player span.

## 3. eval-service — per-player hierarchical judging

- [x] 3.1 Round/game judging grades holistically for a given player, given that player's child
      verdicts (scores + rationales) as context (not a numeric average); produce a verdict with the
      usual dimensions + overall, attributed to that player.
- [x] 3.2 Verdict/target schema carries `player`; write-back records `player` on the evaluation event.
- [x] 3.3 Tests: round verdict for player X considers X's move verdicts; game verdict considers X's
      round verdicts; per-player verdicts are distinct.

## 4. history-service — player on evaluation events

- [x] 4.1 Evaluation envelope/schema accepts an optional `player` field; stored and returned.
- [x] 4.2 Tests: accept/store/list an evaluation event with `player`.

## 5. dashboard — per-player display + cascade request

- [x] 5.1 Evaluate control can request a cascade (move/round/game), and the queue reflects the
      fan-out (the many sub-evaluations).
- [x] 5.2 Transcript verdict sub-tree shows the `player` on each verdict (chip) and groups/labels
      per-player round/game verdicts distinctly from move verdicts.
- [x] 5.3 A per-player game scorecard (move/round/game scores per player, side by side) so players
      can be compared.
- [x] 5.4 Tests for per-player rendering + cascade request.

## 6. Verification and specs

- [ ] 6.1 eval-service + history-service unit/integration green; dashboard typecheck + tests + lint green.
- [ ] 6.2 Drive the live app via Playwright: request a whole-game cascade on a recorded game, watch
      moves→rounds→game grade in the queue, and read per-player scores in the scorecard + transcript.
- [ ] 6.3 Sync `openspec/specs/` and archive the change.
