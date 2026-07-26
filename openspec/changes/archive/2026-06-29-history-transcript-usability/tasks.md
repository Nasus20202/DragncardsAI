## 1. Global expand/collapse of event bodies

- [x] 1.1 Make each `TranscriptEvent` body (AgentBody/GameBody detail) collapsible, collapsed by default; keep the summary line (seq, actor, phase, score, action label, Actions, timestamp) and the short user prompt bubble always visible.
- [x] 1.2 Add a global Expand all / Collapse all control above the transcript (`history-expand-all`, `history-collapse-all`) wired through an `expandSignal` ({ generation, expanded }) from the workspace into the transcript; each event syncs its `bodyOpen` to the signal on generation change but keeps its own per-event toggle.
- [x] 1.3 Tests: body collapsed by default; per-event toggle opens it; Expand all opens all; Collapse all closes all.

## 2. Search across events

- [x] 2.1 Add a transcript search input (`history-search`) that filters visible events by a case-insensitive match across action label, actor, and payload text (intended_action, reasoning, prompt, stringified arguments/state); keep round headers that still have matching events; show a `history-search-empty` state when nothing matches; do not break auto-follow.
- [x] 2.2 Tests: typing filters events; clearing restores all; no-match shows the empty state.

## 3. Round start/end boundaries

- [x] 3.1 Label the round start header as "Round N — start" and render an end-of-round marker (`history-round-end-{key}`, "Round N — end") after the last event of each round; keep Setup sensible (no spurious end marker). Derive boundaries from a helper in history-rounds.ts.
- [x] 3.2 Tests: a multi-round event list renders start and end markers for each round in order.

## 4. Game → rounds → moves navigation tree

- [x] 4.1 Render a collapsible game → rounds → moves tree in the sidebar (`history-nav-tree`, `history-nav-round-{key}`, `history-nav-move-{seq}`); clicking a move node calls `onSelect(seq)` and scrolls the event into view in the transcript via a per-seq ref map and a `selectedSeq` effect guarded so it does not fight the scroll-lock auto-follow.
- [x] 4.2 Tests: the tree lists rounds + moves; clicking a move calls onSelect with its seq.

## 5. Spec sync

- [x] 5.1 Run `openspec validate history-transcript-usability --strict` and ensure it passes.
