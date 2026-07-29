## 1. Measure before changing anything

- [x] 1.1 Establish what a recorded payload actually costs, from the repository's
      own measurement in
      `services/eval-service/src/eval_service/judge/state_view.py` (~450-470 KB
      per `game_state` event, ~225 KB of it `deltas`), and build a fixture whose
      state events match that size and structure.
- [x] 1.2 Seed a history-service with 122-event and 400-event game-shaped
      timelines and time `GET /games/{id}/events?limit=1000` over real HTTP:
      0.50 s / 26.2 MiB and 2.32 s / 86.0 MiB respectively.
- [x] 1.3 Time `GET /games` on the same data to rule the games listing in or out:
      8 ms, ruled out.
- [x] 1.4 Confirm no index is missing — `ix_events_game_seq (game_id, seq)`
      already exists in `0001_initial` and is what the read's
      `game_id = ? AND seq > ?` ordered by `seq` uses.
- [x] 1.5 Split the 400-event read on the server to locate the cost: database
      read plus payload deserialization 1.5 s, response serialization 3.3 s,
      narrow columns with no payload 3 ms. The payload is the cost at both ends.
- [x] 1.6 Measure the browser half on the 122-event response: `JSON.parse` 96 ms,
      and the transcript's search haystack 25 MiB / 86 ms per keystroke.

## 2. history-service: a timeline read that omits the unbounded fields

- [x] 2.1 Add `Repository.list_event_summaries(game_id, after_seq, limit)`
      returning `StoredEvent`s whose payload has `state` and
      `conversation_context` removed, so callers render one shape.
- [x] 2.2 Prune in SQL, not in Python, so the omitted values are never
      deserialized or re-serialized: `jsonb - 'key'` on Postgres, `json_remove`
      on sqlite, behind one dialect branch mirroring `commit_event`'s.
- [x] 2.3 Re-attach a two-scalar projection of the state under
      `payload["state"]["game"]`, read as text (`#>>` / `json_extract`, no cast)
      and coerced in Python, so a dotted `stepId` stays a string and a malformed
      value yields a missing label instead of failing the query.
- [x] 2.4 Tolerate a driver that hands a JSON expression back as text rather than
      as a dict, and report a non-object payload as empty rather than raising, so
      one odd row cannot fail a listing.
- [x] 2.5 Add `TimelineEventResponse` (an `EventResponse` plus
      `payload_complete: false`) and `TimelineListResponse` in `schemas/api.py`.
- [x] 2.6 Add `GET /games/{game_id}/timeline` with the events read's cursor
      contract and a higher `limit` ceiling (5000), leaving the events read, its
      ceiling, `GET /games`, snapshots and restore untouched.
- [x] 2.7 Repository unit tests: the state bulk goes and the round/step survive;
      `0.0`/`0.1`/`1.1`/`2.5` stay dotted strings; `roundNumber` 0 stays 0;
      an agent entry loses its conversation and keeps its decision; no `state`
      projection where no state was recorded; paging matches the events read's
      cursor; the envelope identity fields match the full read; unknown game is
      empty.
- [x] 2.8 API unit tests: an entry drops the bulk and keeps the round/step and
      the other payload fields; the timeline response is at least 10× smaller
      than the events response for the same game; the cursor walks and terminates;
      the full payload is still reachable per event; unknown game is empty;
      `limit` and `after_seq` bounds are enforced.
- [x] 2.9 Postgres integration test for the dialect-specific pruning branch and
      the `#>>` text reads, since the unit suite only exercises the sqlite branch.

## 3. dashboard: load the index, refresh incrementally

- [x] 3.1 Add `listHistoryTimelinePage` and share one request builder with
      `listHistoryEventPage`.
- [x] 3.2 Replace `listAllHistoryEvents` with `listAllHistoryTimeline`, walking
      the timeline resource at its 5000 maximum, keeping the 20,000-event safety
      bound and the truncation report, and accepting an `afterSeq` so a walk can
      resume.
- [x] 3.3 Add `fetchHistoryEvent(gameId, seq)`, addressing one event through the
      events read's exclusive cursor (`after_seq = seq - 1, limit = 1`) and
      resolving null when the seq is not recorded — the cursor being exclusive, an
      absent seq yields the *next* event, which must not be mistaken for it.
- [x] 3.4 Point `use-history` at the timeline walk, and add a `refresh()` that
      resumes from the highest loaded `seq` and appends, alongside the existing
      full `reload()`.
- [x] 3.5 Guard the incremental append against a stale response resurrecting a
      timeline after a reload or a game switch, and key its effect so it cannot
      re-trigger itself.
- [x] 3.6 Switch the 15-second poll, the focus/visibility refresh and the
      evaluation-queue settle callback to `refresh()`; keep `reload()` for the
      in-place restore.
- [x] 3.7 Add `payload_complete` to the `HistoryEvent` type, documented as absent
      (and so implicitly complete) on an event from the events read.
- [x] 3.8 Client unit tests: the timeline page hits the timeline route; the walk
      follows the cursor, stops on a short page, requests the 5000 maximum by
      default, reports truncation at the bound, and resumes from a cursor;
      `fetchHistoryEvent` addresses the right seq, handles seq 1, and resolves
      null for an absent seq and an empty page.

## 4. dashboard: full payloads on demand

- [x] 4.1 Add `useEventDetail(gameId, seq, enabled)`: fetches once, only while
      enabled, never re-fetches a loaded event, and surfaces loading and error.
- [x] 4.2 Fetch from the transcript event when its body opens and its payload is
      reduced; render the body from the fetched event, a spinner while loading,
      and the error otherwise.
- [x] 4.3 Component tests: opening a body fetches the event; a collapsed
      transcript fetches nothing; an already-complete payload is not re-fetched;
      a failed fetch is reported instead of an empty body.

## 5. dashboard: endless scroll

- [x] 5.1 Add `transcript-window.ts` — `tailWindow`, `windowFrom`,
      `extendOlder`, `extendNewer`, `isAtOldest`, `isAtNewest`, `refitWindow`,
      `windowContaining` — as pure functions over half-open indices into the
      filtered primary events, so search and jumps address the window the same way.
- [x] 5.2 Render `primary.slice(window.start, window.end)` in the transcript,
      opening at the tail.
- [x] 5.3 Grow the window from an `IntersectionObserver` on a sentinel at each
      edge, with an explicit button as the accessible and
      no-IntersectionObserver fallback, and show each sentinel only while that
      direction has more to give.
- [x] 5.4 Re-fit the window during render when the filtered list length changes:
      keep following the tail if it was, stay put if parked, and never carry
      forward a window narrower than a screenful — a zero-match search collapses
      it to nothing and clearing the search must not leave one row behind.
- [x] 5.5 Make "Jump to latest" move the window as well as the scroll position,
      and offer it whenever the window stops short of the newest loaded event.
- [x] 5.6 Unit tests for every window function, including the distant-jump
      rebuild and the collapsed-window recovery.
- [x] 5.7 Component tests on a 200-entry timeline: only a window renders and it is
      anchored at the newest events; older loads on demand and keeps the tail;
      repeated loading reaches the first event; a short timeline renders whole
      with no sentinels.

## 6. dashboard: jump to a round

- [x] 6.1 Add the `RoundJump` control, built from the Hero UI `Select` the
      dashboard already uses in `SelectField`, listing rounds from `buildNavTree`
      so it and the navigation tree cannot disagree; skip empty rounds and render
      nothing when there are none.
- [x] 6.2 Leave the control unselected so choosing the same round twice jumps
      twice — it is an action, not a stored setting.
- [x] 6.3 Place it in the transcript toolbar beside the search field, driven by
      the workspace's existing `navigateToEvent`.
- [x] 6.4 Bring the transcript's window to a selection that falls outside it, so
      a round jump and a navigation-tree click into a distant round both render
      their target; rebuild around a distant target rather than spanning the gap.
- [x] 6.5 Component tests: the option list is Setup / Round 1 / Round 2 on
      DragnCards' completed-round convention; choosing a round jumps to its first
      move; choosing Setup jumps to the setup band; nothing renders with no
      rounds or with an empty round.
- [x] 6.6 Workspace test that the control is rendered in the same toolbar row as
      the search field.
- [x] 6.7 Check the round and step vocabulary against
      `external/dragncards-mc-plugin/json/steps.json` — nine steps, `0.0`
      Beginning, `1.1`/`1.2` Player, `2.1`-`2.5` Villain, `0.1` End — and confirm
      DRA-9's `STEP_PHASES` table and `roundNumber + 1` numbering are reused
      rather than re-derived.

## 7. Measure again

- [x] 7.1 Re-time the whole-timeline read over real HTTP: 122 events 0.50 s /
      26.2 MiB → 0.14 s / 82 KiB; 400 events 2.32 s / 86.0 MiB → 0.57 s /
      262 KiB.
- [x] 7.2 Time the steady-state refresh with nothing new: 2.32 s / 86.0 MiB →
      1.4 ms / 58 B on the 400-event game.
- [x] 7.3 Time the new per-event cost the change introduces: 7 ms / 428 KiB for
      one expanded event.
- [x] 7.4 Re-measure the browser half on the 122-event game: `JSON.parse` 96 ms →
      under 1 ms; search haystack 25 MiB / 86 ms → 44 KiB / under 1 ms.
- [x] 7.5 Record all of it in the proposal, with the two caveats stated: the
      figures are against sqlite because no Postgres was available and the Docker
      stack was off limits, and the React render half was not timed in a browser
      for the same reason.

## 8. Checks

- [x] 8.1 `./scripts/lint.sh --fix`.
- [x] 8.2 `./scripts/test.sh unit` for every service, with before and after counts.
- [x] 8.3 `pnpm typecheck` in `services/dashboard`.
- [x] 8.4 `openspec validate --all`.
- [ ] 8.5 Integration tests and a browser pass over the running stack — deferred
      to the orchestrator, which runs them after merge; four sibling agents were
      working concurrently and would have collided on ports.
