# Transcript re-render cost that no longer grows with the length of the history

## Why

The Play transcript got slower the longer a session ran, and the reported symptom
— "react UI should not render the whole chat history for performance reasons" —
pointed at the mounted node count. Measurement says otherwise.

Both transcripts render every event, and neither memoises anything. A streamed
token replaces one event inside one job, but the new `jobs` array identity made
React re-render *every* block in the whole session, re-running `aggregateEvents`
per job and re-parsing the markdown of every settled response. The cost of a
single token therefore grew with the length of the history:

| transcript shape | per streamed token, before | after |
| --- | --- | --- |
| 1 job, 500 events | 118 ms | 3.3 ms |
| 1 job, 1000 events | 258 ms | 7.7 ms |
| 6 jobs, 960 events | 190 ms | 1.4 ms |
| 10 jobs, 3000 events | 641 ms | 5.0 ms |

At 3000 events one token cost two thirds of a full mount, so a streaming response
froze the tab. The History transcript has the same shape without streaming: every
event re-rendered on each selection click, each search keystroke, and each 15 s
poll refresh — 480 ms per click and 517 ms per keystroke at 2000 events.

The mounted node count, by contrast, is not the bottleneck. A real 485-event
session mounts 2 348 elements over 18 000 px, and a browser scroll across six
times that (14 073 elements, 108 000 px) holds a 16.7 ms median frame with no
frame over 32 ms. Windowing the scroll container would have bought nothing
measurable while putting the newly landed follow lock — its gesture handlers,
8 px at-bottom tolerance, content `ResizeObserver` and re-engage control — at
risk, because all of those depend on the container's real scroll geometry.

## What Changes

- **dashboard (Play transcript)** — the reasoning, compaction, model-output and
  collapsible tool/skill/subagent blocks, and the job thread that holds them, SHALL
  be memoised, and each thread's event aggregation SHALL be memoised on its event
  list. A streamed token then re-renders only the response it changed. The
  transcript's rendered output is unchanged.
- **dashboard (History transcript)** — the event row SHALL be memoised, which
  requires the props handed to every row to be referentially stable: the empty
  verdict list, the default expand and reveal pulses, the restore callback and the
  board-action bundle. A row SHALL receive the current selection only when it owns
  one of the selected verdicts, so moving the selection touches two rows instead of
  all of them.
- **dashboard (regression guard)** — the suite SHALL assert the re-render
  containment directly by counting renders, so the memoisation cannot be silently
  undone by a later prop change.

## Non-goals

- No windowing or virtualisation of either transcript. The measurements above say
  the mounted node count is not the bottleneck, and virtualising the container is
  the change most likely to break the follow lock.
- No change to the follow lock, the scroll geometry, or any transcript visuals.
  The rendered DOM is byte-identical before and after.
- No change to initial mount cost, which is ~1 s at 3000 events and unaffected by
  memoisation. It is a one-off on session load, not a per-token cost.
- No new dependencies.
