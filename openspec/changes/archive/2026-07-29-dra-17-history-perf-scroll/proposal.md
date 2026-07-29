# Make the history view fast, and page it by scrolling

## Why

DRA-17 reports that the history-service API calls take over ten seconds, and asks
for endless scroll on the history page with a way to jump straight to a round.

The three are one problem. DRA-9 made the history view load a game's **whole**
timeline by following the `after_seq` cursor to the end, which was the right fix
for "only the first 100 events are shown" but made the view pay for every
recorded payload up front. A `game-service` history event embeds the raw
DragnCards room state, and this repository has already measured that payload:

> Measured on real recorded games that payload is ~450-470 KB, of which ~225 KB
> is `deltas` (DragnCards' internal undo/replay log) and most of the rest is
> plugin configuration: layouts, automation action lists, rule definitions, image
> URLs, and both faces of every card definition including artwork geometry.
>
> — `services/eval-service/src/eval_service/judge/state_view.py`

So the read is not slow because of a missing index or an N+1. It is slow because
it is enormous, and the size is entirely payload the history view does not
display until a reader opens one event.

### What was measured

A history-service instance was seeded with game-shaped timelines (alternating
`agent` decisions and `game-service` `game_state` events) whose states are built
to the size documented above — 466 KiB of JSON per state event, with the same
`deltas` / `cardById` / `groupById` / `playerData` structure — and served with
uvicorn on a loopback port. Timings are `curl`'s `time_total`, best of three,
and cover the whole request: database read, deserialization, response-model
validation, JSON serialization, and transfer.

| request | 122-event game | 400-event game |
| --- | --- | --- |
| `GET /events?after_seq=0&limit=1000` | **0.50 s**, 26.2 MiB | **2.32 s**, 86.0 MiB |
| `GET /games` | 0.008 s | 0.008 s |

Splitting the 400-event read on the server showed where the time goes: the
database read plus deserializing the payloads into Python is 1.5 s, and
serializing them back out is 3.3 s. Selecting the narrow columns and no payload
at all is 3 ms. The payload *is* the cost, at both ends.

The browser then pays for the same bytes again. Parsing the 122-event response is
96 ms in V8 and the transcript's search haystack (`eventSearchText`, which
stringifies `payload.state`) is 25 MiB and 86 ms to build — per keystroke. On top
of that the workspace re-runs the whole walk every 15 seconds, on window focus,
and on every visibility change, so a 400-event game re-downloads 86 MiB three or
four times a minute for the entire time the tab is open.

`GET /games` was measured and is not implicated: 8 ms. The `(game_id, seq)` index
the events read needs already exists (`0001_initial`), so no index is missing.
The ten seconds the issue reports is this read plus the Next.js proxy hop plus
the browser's parse and render of tens of megabytes; the 2.3 s server-side floor
measured here is the part that is unambiguously the service's own.

### Why scrolling and round-jump belong in the same change

Once the listing stops carrying payloads, the view holds a small index of the
game and can render a window of it instead of all of it — which is what endless
scroll is. And once only a window is rendered, scrolling is no longer a way to
reach round 2 of 15, so a jump-to-round control stops being a nicety and becomes
the way to navigate. Each of the three deliverables is what makes the next one
possible.

## What Changes

- **history-service — a timeline read.** A new
  `GET /games/{game_id}/timeline` lists a game's events with the two unbounded
  payload fields removed: `state` (the raw room state) and
  `conversation_context` (an agent move's whole conversation). It keeps the exact
  cursor contract of the events read (`after_seq` in, `next_after_seq` out, same
  ascending `seq` order) so a client walks one the way it walks the other, and it
  keeps the same entry shape so nothing downstream has to branch — plus a
  `payload_complete: false` flag that says the payload was reduced.

  `payload["state"]` is not dropped outright but reduced to
  `{"game": {"roundNumber": …, "stepId": …}}`, which is exactly what DRA-9's round
  and phase labels read. The reduction is a projection of the recorded state with
  its shape preserved, in the same spirit as eval-service's `project_state`.

  The pruning happens **in the database** — `jsonb - 'key'` on Postgres,
  `json_remove` on sqlite — so the omitted values are never deserialized into
  Python and never serialized into a response. Round and step are read as
  *text* (`#>>` / `json_extract`, no cast) and coerced in Python, because
  `stepId` is a dotted string: a JSON-typed read would turn step `0.1` into the
  float `0.1`, and a failed integer cast would take the whole listing down rather
  than yield a missing label.

  The per-request `limit` ceiling is 5000 rather than the events read's 1000,
  because an entry is a few hundred bytes instead of a few hundred kilobytes.

  The events read, its `limit` ceiling, its response shape, `GET /games`,
  snapshots and restore are all untouched.

- **dashboard — load the index, not the payloads.** `use-history` walks the
  timeline resource instead of the events resource. A refresh
  (`refresh()`) resumes from the highest `seq` already held rather than
  re-reading the game, so the 15-second poll and the focus/visibility refresh
  cost what was recorded since the last look instead of the whole game. The full
  reload (`reload()`) remains for the cases that genuinely need it.

- **dashboard — full payloads on demand.** An event's detail body is where
  `state` and `conversation_context` are actually shown, so that is where the
  complete event is fetched: `useEventDetail` requests it the first time a body
  is opened, once per event, through the events read's existing exclusive cursor
  (`after_seq = seq - 1, limit = 1`). No new endpoint.

- **dashboard — endless scroll.** The transcript renders a contiguous window of
  the filtered primary events, opening at the newest end, and grows it when the
  reader reaches an edge — watched by an `IntersectionObserver` on a sentinel,
  with an explicit "Show earlier events" / "Show later events" button as the
  accessible and no-IntersectionObserver fallback. The window logic is pure
  functions in `transcript-window.ts` so it is testable on its own: opening at
  the tail, growing either way, re-fitting when the list length changes under it
  (a search keystroke, or an append from live play), and rebuilding around a
  distant jump target rather than spanning the gap to it.

  Auto-follow and the scroll lock keep working: "Jump to latest" now moves the
  window as well as the scrollbar, and is also offered whenever the window stops
  short of the newest event, which is where a round jump leaves it.

- **dashboard — jump to a round.** A new `RoundJump` control sits in the
  transcript toolbar beside the search field and lists the rounds from the same
  `buildNavTree` breakdown the sidebar navigation tree uses, so both name rounds
  identically — "Setup", then "Round N" on DragnCards' completed-round
  convention. Choosing one selects that round's first move; the transcript
  already scrolls a selection into view and now also brings its window along, so
  a navigation-tree click into a distant round works for the same reason.

## Non-goals

- **Changing the events read.** Its shape, its `limit` ceiling and its callers
  (eval-service's `HistoryClient`, restore replay) are left alone. The timeline
  read is additive.
- **Storing a denormalized summary.** Columns on `events` for the round, the step
  and a pre-pruned payload, filled at ingest, would take the listing from 0.58 s
  to a few milliseconds on a 400-event game. It was rejected as too much for the
  measured problem: it needs a migration, a backfill that rewrites every existing
  row, a write-path change, and it duplicates data that the pruning query already
  produces cheaply enough. The residual 0.58 s is a one-time cost per game
  opened, after which refreshes are incremental and measured at 1.6 ms.
- **Virtualizing with a windowing library.** The transcript's rows vary in height
  and carry sticky round headers; a contiguous grown window is enough to bound
  the DOM without a measurement-based virtualizer.
- **Changing how producers emit events.** Post-action state stays the contract.
- **Restyling the history view.** The toolbar gains one control built from the
  Hero UI `Select` the dashboard already uses in `SelectField`; nothing existing
  is re-themed.
- **Searching the raw game state.** With the listing pruned, the transcript's
  search no longer matches text inside `payload.state`'s card definitions and
  delta log. That is a deliberate improvement as well as a consequence: those
  25 MiB of plugin configuration and undo log were never what a reviewer was
  searching for, and building the haystack from them cost 86 ms per keystroke on
  a 122-event game.

## Impact

- Affected specs: `history-event-store` gains the timeline read requirement;
  `game-history-ui` gains endless scroll, jump-to-round and on-demand payload
  requirements, and its complete-timeline requirement is modified to name the
  timeline resource.
- Affected code: `services/history-service/src/history_service/storage/repository.py`,
  `.../schemas/api.py`, `.../api/routers/events.py`;
  `services/dashboard/features/history/lib/history-api.ts`,
  `.../lib/use-history.ts`, `.../lib/transcript-window.ts` (new),
  `.../lib/use-event-detail.ts` (new),
  `.../components/history-transcript.tsx`, `.../components/history-workspace.tsx`,
  `.../components/round-jump.tsx` (new), and
  `services/dashboard/features/shared/lib/types.ts`.
- No database migration, no schema change, no configuration change.

## Results

Same harness, same fixtures, after the change:

| request | 122-event game | 400-event game |
| --- | --- | --- |
| whole timeline, one page — before (`GET /events?limit=1000`) | 0.50 s, 26.2 MiB | 2.32 s, 86.0 MiB |
| whole timeline, one page — after (`GET /timeline?limit=5000`) | **0.14 s**, 82 KiB | **0.57 s**, 262 KiB |
| 15-second refresh with nothing new — before | 0.50 s, 26.2 MiB | 2.32 s, 86.0 MiB |
| 15-second refresh with nothing new — after | **0.0013 s**, 58 B | **0.0014 s**, 58 B |
| one expanded event's full payload (new cost) | 0.007 s, 428 KiB | 0.007 s, 428 KiB |
| `GET /games` (untouched) | 0.008 s | 0.008 s |

Browser-side, on the 122-event game: `JSON.parse` of the response drops from
96 ms to under 1 ms, and the transcript's search haystack from 25 MiB / 86 ms per
keystroke to 44 KiB / under 1 ms.

Two caveats stated plainly. First, these numbers are against sqlite, the dialect
the unit suite uses, because no Postgres was available in this environment and
the brief forbade starting the Docker stack; the ~0.5 s residual in the pruned
read is sqlite parsing JSON *text*, which Postgres's pre-parsed `jsonb` does not
do, so the Postgres figure should be at least as good but is unverified. The
Postgres pruning branch is dialect-specific SQL and is covered by a new test in
`tests/integration/test_postgres_repository.py`, which runs when the stack is up.
Second, the render half of the ten seconds — React mounting hundreds of event
rows — was not measured end to end for the same reason; the window bounds it by
construction, and the bound is tested (a 200-entry timeline renders at most 60
rows), but no browser timing was taken.
