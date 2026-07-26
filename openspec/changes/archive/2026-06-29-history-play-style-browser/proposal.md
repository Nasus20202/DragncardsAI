# Play-style history browser

## Why

The history view today is a cramped master-detail: a narrow left timeline of one-line
rows, and a separate panel that shows the *one* selected event. To read a whole game you
click row by row, and the reading area only ever holds a single event. The Play tab solves
exactly this problem for live sessions — a left **sessions list** plus a **continuous,
vertically-scrolling transcript** of the whole conversation — and users have asked to browse
recorded games "the same way as the Play tab".

## What Changes

- Replace the header `<select>` game picker with a **left games-list sidebar** that mirrors
  Play's `PlaySessionList`: one row per recorded game (friendly name → falls back to id,
  event count, last-activity, a status dot), collapsible, with the existing delete affordance
  moved onto the row. Selecting a game loads its history.
- Replace the narrow timeline + single-event detail panel with a **continuous whole-game
  transcript** that mirrors Play's `PlayTranscript`: every event rendered inline as a readable
  block in one scrollable column, grouped under sticky round headers, in ascending `seq`.
  - `agent_move` events render their intended action + reasoning and the captured
    conversation transcript (reusing the existing readable-transcript renderer).
  - `game_state` events render a concise board/status summary (action label, phase chip).
  - `user_prompt` events (once landed) render as a "User" prompt bubble that triggered the
    agent — the Play-tab prompt-bubble styling.
  - Evaluator verdicts stay nested as the collapsible "▸ N evaluations" sub-tree under the
    graded event (unchanged behavior, now inline in the transcript).
  - Scroll-lock auto-follow + "Jump to latest" behavior is reused so a game still being played
    in another tab streams in naturally.
- Per-event actions (restore here, open board here) move from a fixed right-hand controls
  column to **inline affordances on the focused event** (the transcript row the user is on),
  so they stay reachable without a separate column. Game-level **Evaluate** stays as the
  header button + drawer (unchanged).
- Keep the responsive/scroll-safe guarantees: no horizontal overflow, independent scroll
  regions, the games list collapses on narrow widths.

This change is additive UI restructuring on the dashboard only; the history-service event/
snapshot/restore contracts are unchanged.

## Impact

- Affected specs: `game-history-ui` (timeline view → games-list + continuous transcript;
  per-event actions; retains restore/board/eval requirements).
- Affected code: `services/dashboard/features/history/` — new `history-games-list.tsx` and
  `history-transcript.tsx` (mirroring the Play equivalents), `history-workspace.tsx` recomposed
  into list + transcript, reusing `history-detail.tsx`'s transcript renderer, `restore-control`,
  `board-control`, and the evaluation drawer. No backend changes.
- Out of scope: changing what events are recorded, the restore/reconstruction mechanics, or the
  evaluation flow.
