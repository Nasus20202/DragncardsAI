# Label a round verdict with its round of play, not with its sequence span

## Why

`verdictScopeLabel` in
`services/dashboard/features/history/lib/history-rounds.ts` renders a round
verdict's `payload.round_span` as if its two elements were round numbers:

```ts
const from = span[0];
const to = span[span.length - 1];
return from === to ? `Round ${from}` : `Rounds ${from}–${to}`;
```

`round_span` is a **sequence** pair, not a round range.
`services/eval-service/src/eval_service/runtime/evaluator.py` sets it as
`[rnd.from_seq, rnd.to_seq]` for round scope (and `[game.from_seq,
game.to_seq]` for game scope). Confirmed against the recorded game
`35128894-0cad-4b53-b195-d74b7428fe2c`, whose rounds are seqs 1–63, 64–103 and
104–124: the verdict for its **first** round reads **"Rounds 1–63"** in the
transcript, next to a round band the very same file labels "Round 1 — start".

The defect predates DRA-14 and is independent of it. DRA-14 fixed *which* seqs a
round span covers; this is a defect in how that span is *labelled*, and it would
have read just as wrongly under the old spans. DRA-14's proposal recorded it as
an explicit non-goal wanting its own issue, on the grounds that the verdict
payload "carries no round number to label with" — which is exactly the gap this
change closes.

The same expression appears a second time in `targetScopeLabel`
(`services/dashboard/features/history/lib/eval-queue.ts`), reading
`TargetSummary.round_span` — also a seq pair — so the evaluations queue row for
that round reads "Rounds 1–63" too.

## What Changes

### The round of play travels on the verdict, and is not re-derived from seqs

- **eval-service (verdict payload)** — `VerdictPayload` gains
  `round_number: int | None`: the **1-based round of play** the verdict grades.
  It is populated for `scope=round` from `RoundInput.round_number`, which
  `detect_round_boundaries` has already converted through
  `assembly.round_of_play()` (raw `roundNumber` + 1). Move and game verdicts
  leave it `None` — a move verdict is labelled by its move and a game verdict
  covers every round, so neither has a single round to name.
- **eval-service (naming)** — `round_span` keeps its meaning and its name: it is
  the seq span, the thing that seq-correlates a verdict to the timeline, and it
  stays on the payload. The two fields now say two different things explicitly,
  which is what makes reading one as the other a spotted error rather than a
  plausible mistake.
- **dashboard (verdict label)** — `verdictScopeLabel` labels a round verdict from
  `payload.round_number` and **never** from `round_span`. There is one place in
  the dashboard that turns a round number into a label — `roundHeading`, already
  used for the transcript's round bands and its navigation tree — and the verdict
  label now goes through it, so a verdict and the band it sits inside cannot
  disagree about what a round is called.
- **dashboard (queue label)** — `targetScopeLabel` stops rendering a round
  target's seq span as round numbers. A queue row is bookkeeping identified by
  sequence, and already labels its other scopes that way (`Move #12`, `Range
  #10–#18`), so a round target reads `Round #64–#103` — the span it actually
  holds, in the seq notation the rest of the row uses.

### What happens to verdicts already recorded

Nothing is rewritten, re-scored, or deleted, and no verdict is re-labelled by
guesswork:

- A round verdict recorded **before** this change carries no `round_number`. It
  is labelled `Round`, with no number — accurate about the scope, silent about
  which round. Its `round_span` is still shown in the verdict detail, where it is
  presented as the seqs it is.
- That covers **`eval-1`** verdicts, whose spans were shifted by one event at
  each boundary (DRA-14), so resolving one against today's boundaries would name
  a round that verdict did not grade. It also covers `eval-2` verdicts recorded
  before this change, which `evaluator_version` alone cannot distinguish from
  later ones. The **presence of the field**, not the version tag, is what decides
  whether a number is shown, so both cases are handled by one rule and neither is
  mislabelled.
- A user who wants the number on an old verdict re-runs the evaluation with
  `force`, which is the same answer DRA-14 gave for re-grading.

`EVALUATOR_VERSION` stays `eval-2`. The version identifies what the judge was
**shown and asked**; this change adds a field describing what was already graded
and alters neither the prompt, the span, nor the scale. Bumping it would falsely
declare `eval-2` scores incomparable with each other.

### Alternative considered and rejected: resolve the span in the UI

The dashboard already computes round boundaries per seq (`buildMetaBySeq`), and a
round verdict's `target_seq` is its closing seq, so `metaBySeq.get(target_seq)`
would yield a round number with no schema change at all. Rejected:

- It makes the label depend on client-side boundary detection agreeing with the
  service's, which is a second derivation of the same fact and free to drift —
  DRA-14 is the precedent, having changed exactly that derivation on one side.
- It silently mislabels `eval-1` verdicts. Their spans are shifted by one event
  at each boundary, so a resolution succeeds and returns a round the verdict did
  not grade — the worst outcome available, since a wrong number is
  indistinguishable from a right one.
- A verdict's round is a property of what was graded, so it belongs to the
  recorded verdict, not to whatever the client can re-derive later.

A third option — carrying the round number on the queue's target row as well —
was rejected for the queue specifically: a target row is created before the
target is graded, so a stored round number there is a durable copy of a derived
value that can go stale if boundary detection changes again. On a verdict the
number is a record of what was actually graded and cannot go stale.

## Non-goals

- Round-boundary detection, in either service. Which seqs a round covers is
  DRA-14's settled answer and is not reopened; only the label changes.
- Backfilling, migrating, or re-grading verdicts recorded without
  `round_number`.
- Any change to `round_span`: it keeps its name, its shape, and its place on the
  payload and on the queue's target summaries.
- A round number on the evaluations queue's target rows (which would need an
  eval-service schema column, and would store a derived value before it is
  known).
- The `range`-scope verdict label, which already renders its span in seq
  notation (`Range #10–#18`) and is therefore not wrong.

## Impact

- Affected specs: `agent-move-evaluation` (the written-back verdict identifies
  the round of play it grades, distinct from its seq span) and `game-history-ui`
  (a round verdict is labelled by its round of play, and a verdict with no
  recorded round number is not given one).
- Affected code:
  - `services/eval-service/src/eval_service/schemas/verdict.py` (`round_number`),
    `judge/parse.py` (pass-through), `runtime/evaluator.py` (populate it at round
    scope).
  - `services/dashboard/features/shared/lib/types.ts`
    (`HistoryEvaluatorPayload.round_number`),
    `features/history/lib/history-rounds.ts` (`verdictScopeLabel`),
    `features/history/lib/eval-queue.ts` (`targetScopeLabel`).
- Affected docs: `services/eval-service/README.md` (verdict payload) and
  `services/eval-service/AGENTS.md` (the round-boundary rule gains the
  `round_span` vs `round_number` distinction).
- No database schema change, no migration, and no API-breaking change: the new
  payload field is optional and additive, and every existing field keeps its
  meaning.
