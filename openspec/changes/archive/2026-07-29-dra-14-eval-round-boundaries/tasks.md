# Tasks

## 1. Confirm the defect against the code and the ground truth

- [x] 1.1 Re-check the post-action premise in the producer: `game-service`
      `session.py` fetches a fresh state after applying the action before
      emitting, and both it and `history_emitter.py` say "post-action state".
- [x] 1.2 Re-check the round-counter premise: `roundNumber` counts COMPLETED
      rounds (`skills/marvel-champions-play/resources/reading-state.md`; DRA-9's
      archived proposal cites `actionLists.json` `villainEndPhase`), and confirm
      DRA-9 settled on `roundNumber + 1` for display in
      `services/dashboard/features/history/lib/history-rounds.ts`.
- [x] 1.3 Trace `detect_round_boundaries` and confirm it closed a round at
      `last_seq_in_round` (the seq BEFORE the round-number change) and reported
      the raw counter.
- [x] 1.4 Enumerate every consumer of the boundary tuple so the blast radius is
      known: `assemble_round_input` (span, `round_number`, closing state),
      `runtime/requests.py` (`_selected_round_spans`, whole-game span expansion),
      `runtime/evaluator.py` (`_round_span` dependency window),
      `runtime/players.py` (`_round_bounds` seat attribution).
- [x] 1.5 Establish that the graded MOVE set per round does not change: the
      round-changing event is always a `game-service` event and nothing else sits
      between the old and new closing seq — so seat attribution and per-player
      round fan-out are unaffected, while the closing seq and closing board are.
- [x] 1.6 Confirm step ids are not involved (eval reads `roundNumber` only), so
      DRA-9's third defect has no eval-service counterpart.

## 2. Fix boundary detection

- [x] 2.1 Close a round AT the event whose post-action state reports the new
      round number, and start the next round at that seq + 1.
- [x] 2.2 Guard the terminal path so an event that both closes a round and
      carries a terminal status closes it once and cannot append an inverted,
      empty span.
- [x] 2.3 Add `round_of_play()` (raw + 1) and report rounds of play from
      `detect_round_boundaries`; document `round_number_of` as the RAW counter.
- [x] 2.4 Document the post-action rule and the numbering in the function
      docstring, on `RoundInput.round_number`, and where the round-closing state
      is resolved (a round-change close now lands ON a state event; only a
      trailing open round still needs DRA-7's fallback).
- [x] 2.5 Note in `_selected_round_spans` and on `Selection.rounds` that a
      selected round number is a round of PLAY, not the raw counter.

## 3. Surface the comparability break

- [x] 3.1 Default `EVALUATOR_VERSION` to `eval-2`, with the reason on the field
      itself, and mirror it in `.env.example` and `docker-compose.yaml`.
- [x] 3.2 Document in the service README ("Round boundaries") what changed, that
      `eval-1` round/game verdicts are not comparable to `eval-2` ones, and that
      `evaluator_version` on each verdict is what distinguishes them.
- [x] 3.3 Record the rule in `services/eval-service/AGENTS.md`: post-action
      boundaries, 1-based rounds, and bump `EVALUATOR_VERSION` rather than
      silently re-scoping stored verdicts.

## 4. Tests

- [x] 4.1 `tests/unit/test_assembly.py` — new `_dra14_recorded_game()` fixture
      pinned to the real game's seqs (raw `roundNumber` 0 → 1 at seq 63, 1 → 2 at
      seq 103, seq 63 being the `next_step` that closed the first round of play):
      spans are `(1, 1, 63)`, `(2, 64, 103)`, `(3, 104, 122)`, and 62/102 are NOT
      closing seqs.
- [x] 4.2 `tests/unit/test_assembly.py` — rounds are numbered as rounds of play
      (`[1, 2, 3]`, never 0) and `round_of_play(0) == 1`.
- [x] 4.3 `tests/unit/test_assembly.py` — the `next_step` that closed a round is
      in that round's graded moves, and the round's closing state is the state
      recorded at its closing seq (one completed round), not the earlier board.
- [x] 4.4 `tests/unit/test_assembly.py` — a round change and a terminal status on
      the same event close the round exactly once, with no empty trailing span.
- [x] 4.5 Re-point the tests that encoded the off-by-one to the corrected spans
      and round-of-play numbers: `test_assembly.py` (change/terminal detection,
      terminal fallback, round-input span, non-strategic omission, closing-state
      fallback now exercised via a trailing OPEN round that ends on an agent
      move), `test_requests.py`, `test_cascade.py` (including `rounds=[2]` for
      the raw-1 round), `test_config.py`, and the integration
      `test_worker_end_to_end.py` round spans.
- [x] 4.6 Verify all four new tests FAIL against the pre-fix detection (a
      temporary pytest plugin restoring the old algorithm, removed afterwards):
      4 failed — including `BoundaryUndetectedError: seq 63 is not a detected
      round-closing boundary`, which is the bug stated exactly.

## 5. Checks

- [x] 5.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh`.
- [x] 5.2 `./scripts/test.sh unit eval-service` — 178 → 182 passed.
- [x] 5.3 `openspec validate --all` — only the pre-existing
      `spec/typed-game-actions` failure remains.
- [ ] 5.4 Integration suite and Playwright verification (run by the orchestrator
      after merge; four agents share this stack, so no Docker was started here).
