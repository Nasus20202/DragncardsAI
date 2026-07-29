# Close an eval-service round at the event that closed it

## Why

`eval-service`'s `detect_round_boundaries`
(`services/eval-service/src/eval_service/judge/assembly.py`) derived round spans
the same way the History UI did before DRA-9, and carries the same two defects
DRA-9 fixed for display. Both are visible in the same ground truth DRA-9 used.

### A round ended one event too early

A `game-service` history event embeds the state **after** its action was applied
(`session.py` fetches a fresh post-action state before emitting; its docstring
says "post-action state"). Boundary detection attributed that state to the event
that caused it, so the event whose state first reports a NEW `roundNumber` — the
event that **closed** the previous round — was filed under the round it opened.
Each round therefore ended at the last seq *before* its own closing action, and
every span was shifted by one event at each boundary.

Confirmed against the real recorded game `35128894-0cad-4b53-b195-d74b7428fe2c`:
raw `roundNumber` goes 0 → 1 at seq 63 and 1 → 2 at seq 103, and seq 63 is the
`next_step` that *ended* the previous round. Pre-fix the spans were
`[1–62]`, `[63–102]`, `[103–122]`; the rounds as played are `[1–63]`, `[64–103]`,
`[104–122]`.

Two consequences, both on judge input:

1. A round roll-up's `target_seq` (its closing seq) was the seq before the close,
   so its `closing_state` — "Game state at round close" in the prompt — was the
   board from *before* the round's own closing action, not the board as the round
   ended. Since DRA-7 made the roll-up fall back to the nearest recorded state
   at-or-before the closing seq, this fell back rather than failing loudly.
2. The round-closing `game-service` event fell in the next round's span, which
   shifts `players_in_span`, the child-verdict collection window, and the seq
   range a round's `count_nonterminal_children` dependency check covers.

The *set of agent moves* per round is unchanged by the fix: the event that
changes the round number is always a `game-service` event, and the seq range
between the old and new closing seq contains nothing else. So no move moves
rounds — but which board a round is graded against, and which seq identifies it,
both change.

### `roundNumber` is a count of completed rounds, so round 1 was called round 0

DragnCards `roundNumber` counts **completed** rounds (`actionLists.json`
`villainEndPhase` does `INCREASE_VAL /roundNumber 1`, and the `0.1` → `0.0` step
wrap increments it too), so it reads 0 for the whole first round of play — as
documented in `skills/marvel-champions-play/resources/reading-state.md` and as
DRA-9 settled for the History UI, which displays `roundNumber + 1`.
`detect_round_boundaries` reported the raw counter, so the judge prompt said
"round 0" for the first round of play and every round after was named one lower
than the transcript names it. `selection.rounds` took the raw counter too, so a
user asking to grade what the History tab calls "Round 2" got the third round.

### Marvel Champions step ids are not a phase band

Recorded for completeness, since it is the third fact DRA-9 established from
`external/dragncards-mc-plugin/json/steps.json`: the nine step ids are dotted
strings whose major digit is not the phase (`0.0` Beginning **opens** a round,
`0.1` End **closes** it). Boundary detection reads `roundNumber` only and never
buckets a step id, so it does not carry this defect and nothing here changes for
it.

## What Changes

- **eval-service (boundary placement)** — a round closes AT the event whose
  post-action state first reports a different `roundNumber`; that event is the
  round's `to_seq` and the next round starts at the seq after it. This mirrors
  DRA-9's History UI rule (a `game-service` event is attributed to the round it
  acted *from*), so an eval round span and the transcript's round band cover the
  same events. An event that both closes a round and carries a terminal status
  closes that round exactly once and does not open an empty trailing span.
- **eval-service (round numbering)** — every round number the service reports or
  accepts is the 1-based round of PLAY (`round_of_play()` = raw + 1): the round
  named in a round prompt, and the numbers in `selection.rounds`. The raw counter
  stays internal to detection. Naming the round of play in `selection.rounds` is
  a behaviour change for a direct API caller that previously sent raw numbers; the
  dashboard never sends `rounds` (it sends `seqs`/`seq_range`/`whole_game`), so no
  UI depends on the old meaning.
- **eval-service (verdict comparability)** — `EVALUATOR_VERSION` defaults to
  `eval-2`. Round and game verdicts recorded under `eval-1` graded a span shifted
  by one event at each boundary and are NOT comparable to `eval-2` ones. Stored
  verdicts are left exactly as recorded — nothing is rewritten or deleted — and
  `evaluator_version`, already on every verdict payload and already shown in the
  History UI's verdict detail, is what tells the two apart. It is also folded into
  the write-back idempotency key, so re-grading a target under `eval-2` records a
  new verdict rather than being deduped against the `eval-1` one.
  - Rejected: a separate `boundary_version` field on the verdict payload. It
    would say precisely which derivation graded a verdict, but the payload shape
    must match the dashboard's `HistoryEvaluatorPayload` exactly, so it costs a
    schema change plus dashboard work to carry information `evaluator_version`
    already carries — that field exists to make "what the judge was asked" a
    traceable version, and this is exactly such a change.
  - Rejected: silently reusing `eval-1`. Old and new round verdicts would be
    indistinguishable in history and would be averaged together on the per-player
    scorecard as if they graded the same thing.
  - Accepted cost: a move verdict's meaning does not change, but its tag does.
    Over-tagging is safe (a reader can see move scope is boundary-independent);
    under-tagging is not.

## Non-goals

- Excluding the setup band from the first round's span. DRA-9 shows "Setup"
  separately in the transcript (`roundNumber` 0 with step `0.0`), but eval spans
  must TILE the timeline: a `whole_game` round/game request expands to targets
  per span, so any move outside every span would never be graded at round scope.
  Setup moves stay in the first round's span and continue to be excluded from the
  graded move list by the non-strategic taxonomy (DRA-7), which is where that
  judgement belongs.
- Re-grading, migrating, or deleting the round/game verdicts already recorded
  under `eval-1`. The change makes them distinguishable, not invalid-by-fiat; a
  re-grade is a user's `force` request, not a migration.
- The History UI's `verdictScopeLabel`, which renders a round verdict's
  `round_span` (a `[from_seq, to_seq]` pair) as if it were round numbers — a
  round verdict spanning seqs 1–63 reads "Rounds 1–63". That is a dashboard
  display defect independent of boundary detection (the payload carries no round
  number to label with) and wants its own issue.
- Step-id phase mapping in eval-service. It reads `roundNumber` only.
- Any change to how producers emit events. Post-action state remains the
  contract; the consumer now interprets it correctly.

## Impact

- Affected specs: `agent-move-evaluation` (per-round evaluation: where a round
  span ends, how rounds are numbered, and that a change in span derivation is
  surfaced through `evaluator_version` rather than silently applied).
- Affected code: `services/eval-service/src/eval_service/judge/assembly.py`
  (`detect_round_boundaries`, new `round_of_play`),
  `services/eval-service/src/eval_service/config.py` (`EVALUATOR_VERSION`
  default), plus documentation of the convention in the service README,
  `AGENTS.md`, `.env.example`, `docker-compose.yaml` and the `Selection` schema.
- No API shape, database schema, or migration changes. Evaluation RESULTS change:
  round and game roll-ups are graded on a different span and against a different
  closing board than before.
- Operational note: a round target left `pending` from before the upgrade points
  at an old closing seq, which is no longer a detected boundary. It is recorded as
  `skipped` with `boundary undetected: seq N is not a detected round-closing
  boundary` through the existing `mark_skipped` path — never graded against a
  guessed span — and the round can be requested again at its correct closing seq.
