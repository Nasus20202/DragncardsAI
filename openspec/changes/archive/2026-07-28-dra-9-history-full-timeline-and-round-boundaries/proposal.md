# Show a recorded game's whole timeline, with correct round boundaries

## Why

DRA-9 reports two defects in the History tab: only 100 of a game's actions are
visible, and round starts and ends are calculated wrongly. They are independent
faults that compound each other.

### Only the first 100 events are shown

`use-history.ts` calls `listHistoryEvents(gameId)` with no options. The
history-service's `GET /games/{game_id}/events` defaults `limit` to 100 (max
1000) and already returns a `next_after_seq` cursor, but the dashboard's
`listHistoryEvents` discards that cursor and no caller ever pages. The UI
therefore renders the first 100 events and gives no sign that anything is
missing.

Measured against real recorded data: game `35128894-0cad-4b53-b195-d74b7428fe2c`
holds 122 events, the transcript stopped at `seq` 100, and the entire third round
of play (seqs 101–122) was invisible.

### Round starts and ends are wrong

Ground truth, from the plugin and from recorded data:

- `external/dragncards-mc-plugin/json/steps.json` defines exactly nine Marvel
  Champions steps with dotted string ids and their phases: `0.0` Beginning,
  `1.1`/`1.2` Player, `2.1`–`2.5` Villain, `0.1` End.
- DragnCards `roundNumber` counts **completed** rounds: it is 0 for the whole
  first round of play and increments as a round closes (`actionLists.json`
  `villainEndPhase` does `INCREASE_VAL /roundNumber 1`, and the step wrap from
  `0.1` back to `0.0` increments it too). The round *in play* is
  `roundNumber + 1` — as documented in
  `skills/marvel-champions-play/resources/reading-state.md`.
- A `game-service` history event embeds the state **after** its action was
  applied (`history_emitter.py`; `session.py` fetches a fresh post-action state
  before emitting, and both say "post-action state" in their own docstrings).

`features/history/lib/history-rounds.ts` gets three things wrong against that
ground truth, all reproducible inside the first 100 events and therefore
independent of the 100-event cut:

1. **Off-by-one numbering.** `roundKey`/`roundHeading` treat the raw
   `roundNumber` as the display round and treat `roundNumber` 0 as "Setup". On
   the real game the entire first round of play (51 moves) was labelled "Setup"
   and the second round of play was labelled "Round 1".
2. **Boundary placement.** `buildMetaBySeq` attributes the post-action state to
   the event that caused it, so the move that *closes* a round is filed under the
   *next* round. Observed: the "Round 1 — start" header rendered at seq 63, which
   is exactly the `next_step` whose pre-action state was the previous round's End
   step — the move that ended a round was shown as opening the new one.
3. **Phase naming.** `phaseName` buckets the step id with `Number.parseInt`
   (band 1 → Player, 2 → Villain, `>= 3` → End, else Beginning). Step `0.1` (End
   of Round) therefore renders as "Beginning" (observed at seq 53: "Beginning
   0.1"), and the `>= 3` branch is dead code — no Marvel Champions step has a
   major band of 3 or more.

Separately, `buildRoundEndBySeq` emits a "Round N — end" marker for the final
round even when that round never ended. An in-progress game claims its last
round ended, and a truncated timeline claims a round ended at the truncation
point — observed pre-fix as "Round 1 — end" rendered after seq 100 purely
because the list stopped there.

The two defects are independent (each round bug reproduces within the first 100
events), but truncation additionally hides whole later rounds and fabricates a
false round-end at the cut point, so both must be fixed to make the transcript
trustworthy.

## What Changes

- **dashboard (complete timeline)** — `listHistoryEvents` gains a
  cursor-following helper and `use-history` uses it: request pages of 1000 (the
  server's per-request maximum) and follow `next_after_seq` until the cursor is
  exhausted. This mirrors the precedent already in the repo,
  `HistoryClient.list_all_events` in
  `services/eval-service/src/eval_service/integrations/history.py`.
  - The server's `le=1000` per-request cap is deliberately left alone. Raising or
    removing it was rejected: the cap bounds per-request database work and
    response size, and raising it only moves the ceiling — a large enough game
    would still truncate. A streaming endpoint (SSE/chunked) was rejected too: a
    new transport for a read that pagination already solves, over an append-only,
    finite timeline.
  - A generous client-side safety bound remains (20 pages × 1000 = 20,000
    events) so a pathological game cannot hang the browser. Because a bound
    remains, truncation must be **disclosed** rather than silent: the UI states
    how many events it is showing out of the game's true total, which is already
    available as `event_count` on the games listing.
- **dashboard (round numbering and phases)** — the display round becomes
  `roundNumber + 1`. "Setup" is reserved for the genuine setup band, identified
  as `roundNumber === 0` **and** `stepId === "0.0"` (the Beginning step of round
  0, before the first player phase), plus any events before a game state is
  known. Step ids are mapped to phases through the plugin's actual
  step-to-phase table instead of a numeric band guess.
- **dashboard (attribution and end markers)** — each `game-service` event is
  attributed to the round/step it acted **from** (the pre-action state), with the
  running state updated afterwards; other actors keep inheriting the latest
  observed state. A round's closing move then falls inside that round. The
  "Round N — end" marker is emitted only where the round actually changes to a
  different round, so an in-progress or truncated tail no longer claims a round
  ended.

## Non-goals

- Changing the history-service `limit` ceiling or adding a new streaming
  endpoint. Server read behaviour is unchanged.
- Virtualizing the transcript's rendering. The fetch bound is generous;
  DOM-scale work is a separate concern.
- Changing `eval-service`'s own `detect_round_boundaries` round assembly
  (`services/eval-service/src/eval_service/judge/assembly.py`), which carries a
  similar post-state attribution. DRA-9 is about the History UI, and changing
  judge inputs is a separate, higher-blast-radius change.
- Altering how producers emit events. Post-action state remains the contract;
  the UI now interprets it correctly.
- Any restyling of the history view.

## Impact

- Affected specs: `game-history-ui` (complete-timeline loading with a disclosed
  bound; correct round numbering, phase naming, and attribution of a round's
  closing move; the round start/end requirement is tightened).
  `history-event-store` is unchanged — it already requires the events read API to
  list a game's events "in `seq` order with paging", which is exactly what the
  dashboard now uses.
- Affected code: `services/dashboard/features/history/lib/history-api.ts`,
  `services/dashboard/features/history/lib/use-history.ts`,
  `services/dashboard/features/history/lib/history-rounds.ts`, and the history
  transcript header that discloses the shown-of-total count.
- No API, schema, or configuration changes.
