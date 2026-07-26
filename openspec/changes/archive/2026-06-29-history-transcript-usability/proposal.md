## Why

The history transcript is hard to scan: every event renders its full body (reasoning, arguments, game state) inline, so a long game becomes an unreadable wall of text. There is no way to find a specific event, round boundaries are only marked at the start (so it is unclear where a round ends), and there is no quick way to jump to a given move. These four usability gaps make a recorded game tedious to review even though the data is all there.

## What Changes

- **dashboard** SHALL collapse each event's detail body by default (summary line only) and provide a per-event toggle plus a global Expand all / Collapse all control to open or close every body at once.
- **dashboard** SHALL provide a transcript search that filters events by a case-insensitive match across the action label, actor, and payload text, with a no-matches empty state, without disturbing the auto-follow scroll behavior.
- **dashboard** SHALL mark both the start and the end of each round in the transcript (a "Round N — start" header and a "Round N — end" marker), with no spurious end marker for the leading Setup band.
- **dashboard** SHALL render a game → rounds → moves navigation tree in the sidebar; selecting a move node selects that event and scrolls it into view in the transcript without fighting the auto-follow scroll-lock.

## Capabilities

### Modified Capabilities

- `game-history-ui`: collapsible event bodies with a global expand/collapse control, transcript search, explicit round start/end boundaries, and a game→rounds→moves navigation tree.

## Impact

- dashboard only; no backend or endpoint changes. Reuses the existing history-rounds helpers and transcript components. All existing transcript testids and behaviors (collapsed-by-default conversation/JSON, eval detail expansion, per-event actions dropdown, scroll-lock auto-follow, queue control) are preserved.
