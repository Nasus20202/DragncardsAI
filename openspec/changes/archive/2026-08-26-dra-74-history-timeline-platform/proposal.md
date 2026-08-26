# Propagate the selected platform through dashboard history reads

## User report

> No history recorded for this game yet.

> 4 events

Interpretation: the History game list reports four recorded events, but selecting
the same game renders the empty-history message. This is independently
reproducible from the previously fixed platform-default bug because the list
confirms stored events exist.

## Root cause

`history-workspace.tsx` already resolves the selected game's platform for board
reconstruction, but it calls `useHistory(gameId)` without that platform. The hook
and history API consequently omit the platform from timeline pagination, complete
event reads, and snapshot reads. History Service defaults those requests to the
DragnCards partition, so a Marvel LCG game can appear in the list while its
selected transcript is empty.

## What changes

- Carry the selected platform, with `dragncards` as the fallback for games whose
  list entry has no platform, into the history hook and every history read used by
  the dashboard.
- Add platform query propagation to timeline pages, paged complete-event reads,
  snapshots, and history exports, including incremental timeline refreshes.
- Pass the same platform into transcript detail loading and keep the existing
  selected-platform board and deletion behavior unchanged.
- Add focused API, hook, and workspace coverage for Marvel URL queries and for a
  selected Marvel game whose recorded event count produces a nonempty transcript.

## Scope boundaries

This change is limited to the dashboard history state and API client plus its
focused tests and OpenSpec artifacts. It does not change shared game selectors,
DRA-69 files, History Service behavior, archived OpenSpec artifacts, or platform
drivers.
