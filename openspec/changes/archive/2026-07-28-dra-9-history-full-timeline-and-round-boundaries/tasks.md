## 1. Load the complete timeline (history-api)

- [x] 1.1 Have `listHistoryEvents` in
      `services/dashboard/features/history/lib/history-api.ts` return the
      response's `next_after_seq` cursor alongside the events instead of
      discarding it.
- [x] 1.2 Add a `listAllHistoryEvents(gameId)` helper in the same module that
      pages with `limit` 1000 and follows `next_after_seq` until exhausted,
      mirroring `HistoryClient.list_all_events` in
      `services/eval-service/src/eval_service/integrations/history.py`.
- [x] 1.3 Bound the helper at 20 pages (20,000 events) and report whether it
      stopped at the bound, so callers can disclose truncation instead of
      silently showing a partial timeline.
- [x] 1.4 Leave the history-service endpoint, its `limit` ceiling, and its
      transport untouched.
- [x] 1.5 Unit tests for the helper: a single page ends pagination; multiple
      pages concatenate in ascending `seq` and pass the previous page's cursor as
      `after_seq`; hitting the page bound stops requesting and reports
      truncation.

## 2. Wire the dashboard to the full timeline

- [x] 2.1 Switch `services/dashboard/features/history/lib/use-history.ts` from
      the single-page `listHistoryEvents(gameId)` call to the paginating helper.
- [x] 2.2 Expose a truncation flag plus the loaded count from `use-history`, and
      resolve the game's true total from the `event_count` already carried on the
      games listing.
- [x] 2.3 Unit tests: a game with more events than one page loads them all
      through the hook; a bounded load exposes the truncation flag and the loaded
      count.

## 3. Disclose "showing N of M"

- [x] 3.1 Render a "showing N of M events" affordance in the transcript header
      when the loaded timeline is shorter than the game's known total, and render
      nothing when the whole timeline is loaded.
- [x] 3.2 Unit test: the affordance appears only when truncated, and carries both
      the loaded count and the total.

## 4. Round numbering and phase naming (history-rounds)

- [x] 4.1 In `services/dashboard/features/history/lib/history-rounds.ts`, make the
      displayed round `roundNumber + 1` in `roundKey`/`roundHeading`.
- [x] 4.2 Reserve "Setup" for events with no known game state and for
      `roundNumber === 0` with step id `0.0`; everything else in round 0 is
      "Round 1".
- [x] 4.3 Replace `phaseName`'s `Number.parseInt` bucketing with the plugin's
      step-to-phase table (`0.0` Beginning, `1.1`/`1.2` Player, `2.1`–`2.5`
      Villain, `0.1` End), dropping the dead `>= 3` branch.
- [x] 4.4 Unit tests: round 0 in a player/villain step renders "Round 1"; the
      `roundNumber` 0 / step `0.0` band renders "Setup"; step `0.1` renders
      "End"; each of the nine plugin step ids maps to its documented phase.

## 5. Attribute events to the round they acted from

- [x] 5.1 Change `buildMetaBySeq` so a `game-service` event is attributed to the
      pre-action round/step (the running state as of that event) and the embedded
      post-action state becomes the running state for subsequent events.
- [x] 5.2 Keep non-`game-service` events inheriting the latest observed state.
- [x] 5.3 Unit test: the event whose post-action state crosses into round N+1 is
      grouped under round N, and the following round's start header lands after
      it.

## 6. No fabricated round end

- [x] 6.1 Change `buildRoundEndBySeq` to emit "Round N — end" only where the
      round actually changes to a different round, never for the last round in
      the loaded timeline.
- [x] 6.2 Unit test: a game still inside its last round gets no end marker for
      it; a multi-round timeline still gets an end marker for every round it
      leaves; the Setup band still gets none.

## 7. Correct the pre-existing tests

- [x] 7.1 Update the existing dashboard test that encoded the old off-by-one
      boundary (round 0 as "Setup", the closing move filed under the next round)
      so it asserts the corrected numbering and attribution.
- [x] 7.2 Check the remaining history transcript/navigation-tree tests for round
      labels baked in from the old numbering and update them.

## 8. Verification

- [x] 8.1 Each new test fails against the pre-fix code and passes after it.
- [x] 8.2 `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` in
      `services/dashboard/`; `./scripts/lint.sh --fix` and
      `./scripts/test.sh unit` at the repo root.
- [x] 8.3 Browser check against the running stack on a game with more than 100
      recorded events: the transcript reaches the last `seq`, the rounds are
      numbered from 1, step `0.1` reads "End", each round's closing move sits
      inside that round, and the in-progress last round shows no end marker.
