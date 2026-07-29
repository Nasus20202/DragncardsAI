# Tasks

## 1. Confirm the defect and pick where the round number comes from

- [x] 1.1 Re-read `verdictScopeLabel`
      (`services/dashboard/features/history/lib/history-rounds.ts`) and confirm it
      renders `round_span[0]`/`round_span[-1]` as round numbers.
- [x] 1.2 Confirm `round_span` is a SEQ pair at both producers:
      `runtime/evaluator.py` sets `[rnd.from_seq, rnd.to_seq]` for round scope and
      `[game.from_seq, game.to_seq]` for game scope.
- [x] 1.3 Confirm the verdict payload carries no round number today
      (`schemas/verdict.py`), so the label cannot be derived from the payload
      alone.
- [x] 1.4 Confirm the round of play is already computed and already correct on the
      producing side: `assembly.round_of_play()` (raw + 1),
      `detect_round_boundaries` reporting rounds of play, `RoundInput.round_number`
      carrying one, and `judge/rounds.round_label` / the `GET /games/{id}/rounds`
      listing consuming it. Reuse that number rather than introducing a second
      conversion.
- [x] 1.5 Enumerate every dashboard surface that renders a round label from a seq
      span so none is left lying: `verdictScopeLabel` (transcript verdict rows) and
      `targetScopeLabel` (`features/history/lib/eval-queue.ts`, queue rows and
      failure lines).

## 2. Carry the round of play on the verdict

- [x] 2.1 Add `round_number: int | None` to `VerdictPayload`, documenting that it
      is the 1-based round of PLAY and that `round_span` beside it is a seq pair
      that must never be read as round numbers.
- [x] 2.2 Thread `round_number` through `parse_verdict`.
- [x] 2.3 Populate it in `runtime/evaluator.py` from `rnd.round_number` at round
      scope; leave it `None` for move and game scope, with the reason stated where
      the game span is built.

## 3. Label from the round number, never from the span

- [x] 3.1 Add `round_number?: number | null` to `HistoryEvaluatorPayload`
      (`services/dashboard/features/shared/lib/types.ts`).
- [x] 3.2 Rewrite `verdictScopeLabel`'s round branch to label from
      `payload.round_number` through the existing `roundHeading` helper — the
      dashboard's single round-number-to-label conversion — and to fall back to a
      plain `Round` when the field is absent, never to a number derived from seqs.
- [x] 3.3 Rewrite `targetScopeLabel`'s round branch to present a round target's
      seq span in the seq notation the row's other scopes already use
      (`Round #64–#103`), and `Round` when the target carries no span.
- [x] 3.4 State on both functions why a seq span is never rendered as a round
      number, so the expression is not reintroduced.

## 4. Tests

- [x] 4.1 `services/dashboard/features/history/__tests__/history-rounds.test.ts` —
      a round verdict pinned to the real recorded game (`round_span: [1, 63]`,
      `round_number: 1`) is labelled "Round 1", and NOT "Rounds 1–63".
- [x] 4.2 Same file — a round verdict spanning seqs 64–103 with `round_number: 2`
      reads "Round 2", so the label follows the round number rather than the span.
- [x] 4.3 Same file — an `eval-1` round verdict with `round_span: [1, 63]` and no
      `round_number` reads plain "Round": no number is invented for it.
- [x] 4.4 Same file — move and game verdicts still read "Move" and "Whole game".
- [x] 4.5 `services/dashboard/features/history/__tests__/eval-queue.test.ts` — a
      queue round target spanning seqs 64–103 reads "Round #64–#103" and not
      "Rounds 64–103".
- [x] 4.6 `services/eval-service/tests/unit/test_player_judging.py` — the
      written-back round verdict payload carries `round_number` equal to the round
      of play (raw `roundNumber` 1 → round 2), while `round_span` stays the seq
      span.
- [x] 4.7 `services/eval-service/tests/unit/test_evaluator.py` — a move verdict's
      payload carries no round number.
- [x] 4.8 Re-point any existing assertion that pinned the old label text.

## 5. Documentation

- [x] 5.1 `services/eval-service/README.md` — add `round_number` to the verdict
      payload example and say what it is next to `round_span`.
- [x] 5.2 `services/eval-service/AGENTS.md` — record under the round-boundary rule
      that `round_span` is a seq pair, `round_number` is the round of play, and a
      consumer labels from the latter.

## 6. Checks

- [x] 6.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh` — clean.
- [x] 6.2 `./scripts/test.sh unit` — eval-service 245 → 246, dashboard 516 → 522;
      game-service 378, agent-orchestrator 418, history-service 152 and shared 27
      unchanged. 1736 → 1743 passed, none failing.
- [x] 6.3 `pnpm typecheck` in `services/dashboard` — clean.
- [x] 6.4 `openspec validate --all` — 15 passed, only the pre-existing
      `spec/typed-game-actions` failure remains.
- [x] 6.5 `./scripts/test.sh integration eval-service` against the already-running
      infrastructure — 13 passed. Docker is not started or stopped from this
      worktree because the stack is shared.
- [x] 6.6 Verify the producing side against the REAL recorded game: run
      `detect_round_boundaries` / `assemble_round_input` / `parse_verdict` over the
      124 events of `35128894-0cad-4b53-b195-d74b7428fe2c` read from the running
      history-service. Boundaries are `[(1, 1, 63), (2, 64, 103), (3, 104, 124)]`
      and the first round's verdict payload is
      `{"scope": "round", "target_seq": 63, "round_span": [1, 63], "round_number": 1}`
      — the exact case that displayed as "Rounds 1–63".
- [x] 6.7 Verify the label in a real browser (Playwright): a two-round game seeded
      into the history-service with one `eval-2` round verdict (round of play
      recorded) and one `eval-1` round verdict (seq span only). The first reads
      "Round 1", inside the transcript's own "Round 1 — start"/"Round 1 — end" band;
      the second reads "Round" with no number; no "Rounds N–M" appears anywhere. The
      seeded game was deleted afterwards.
