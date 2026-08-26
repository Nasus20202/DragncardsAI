# Design: Platform-aware dashboard history reads

## Context

History Service stores independent event and snapshot series for the pair
`(game_id, platform)`. Its read endpoints retain `dragncards` as a compatibility
default for older callers, while the dashboard's recorded-game list reports the
platform for each series. The workspace therefore has enough information to
select the correct partition, but the timeline hook currently receives only the
identifier.

## Decisions

### Resolve the partition at the workspace boundary

`HistoryWorkspace` derives `selectedPlatform` from the selected `HistoryGame` and
uses `dragncards` when the list entry omits `platform`. That resolved value is
passed to `useHistory`, transcript detail loading, board reconstruction, transfer
export, and the existing deletion path. The shared selector remains untouched;
the workspace is the owner of the selected game's history identity.

### Keep platform options alongside cursor options

The history API client accepts `platform` in the options object used for events
and timeline pages. `listAllHistoryTimeline` carries it through every cursor
request, including an `afterSeq` incremental refresh. `fetchHistoryEvent` and
`listHistorySnapshots` accept the selected platform directly because those reads
have no cursor-options object at their public boundary.

The client emits `platform=marvel-lcg` for Marvel LCG reads. It omits the query
for DragnCards, preserving the History Service compatibility default for legacy
games without a platform field and keeping existing URLs stable.

### Treat exports as platform-scoped reads too

An export is a streaming GET of the same recorded history store. The export URL
therefore accepts the selected platform and includes the Marvel query before the
browser navigates to it. Imports remain unchanged because they choose their
target from the bundle and import options rather than reading the selected game.

### Make platform changes invalidate hook work

The hook effects depend on both `gameId` and `platform`. A platform change for an
unchanged identifier starts a fresh full load, resets the cursor, and prevents a
late request from the prior partition from repopulating the transcript. The
incremental refresh uses the same selected platform as its initial load.

## Verification strategy

- API tests assert Marvel query propagation for events, timeline pages, complete
  event detail, snapshots, and export URLs.
- Hook tests assert the selected Marvel partition is supplied to timeline and
  snapshot reads.
- Workspace tests provide a Marvel game with a nonzero event count and assert
  that its mocked recorded event appears in the transcript instead of the empty
  state.
- Dashboard focused tests and TypeScript typechecking provide the implementation
  evidence; broader repository validation remains the parent orchestrator's
  responsibility.
