## 1. Games-list sidebar (Play parity)

- [x] 1.1 Add `history-games-list.tsx` mirroring `PlaySessionList`: collapsible left sidebar,
      one selectable row per recorded game showing friendly name (falls back to id), event count,
      last-activity, and a status dot; per-row delete affordance (reuses the existing confirm dialog).
- [x] 1.2 Wire it into `history-workspace.tsx` in place of the header `<select>` picker; selecting a
      row sets the active `game_id`; preserve the focus/visibility auto-refresh of the games list.
- [x] 1.3 Tests: list renders games with friendly names + counts, selection switches the active game,
      delete affordance opens the confirm dialog, collapse toggles.

## 2. Continuous whole-game transcript (Play parity)

- [x] 2.1 Add `history-transcript.tsx` mirroring `PlayTranscript`: a single scrollable column that
      renders every event inline in ascending `seq` under sticky round headers, with scroll-lock
      auto-follow + "Jump to latest".
- [x] 2.2 Render each event kind inline: `agent_move` → intended action + reasoning + readable
      conversation transcript (reuse the existing renderer from `history-detail.tsx`); `game_state` →
      action label + phase chip + status summary; `user_prompt` → "User" prompt bubble (Play styling);
      evaluator verdicts → the existing collapsible "▸ N evaluations" nested sub-tree under the graded event.
- [x] 2.3 Replace the narrow timeline + single-event detail panel in `history-workspace.tsx` with the
      transcript; remove the now-redundant master-detail split while keeping `selectedSeq` for the
      focused event (drives inline per-event actions + the eval drawer's default target).
- [x] 2.4 Tests: transcript renders all event kinds inline, round headers group events, verdict sub-tree
      expands under its graded event, focusing an event updates the inline actions.
- [x] 2.5 Collapse each agent move's conversation transcript by default behind a per-event toggle
      (`history-conversation-toggle-{seq}`, message count shown) — the full conversation per event made
      the transcript unreadable; it expands on demand. Test asserts collapsed-by-default + expand-on-click.

## 3. Per-event inline actions

- [x] 3.1 Move "Restore here" and "Open board here" from the fixed right-hand controls column to inline
      affordances on the focused transcript event, reusing `RestoreControl` / `BoardOpenControl`.
- [x] 3.2 Keep game-level Evaluate as the header button + drawer (unchanged), defaulting its target to the
      focused event.
- [x] 3.3 Tests: inline restore/board act on the focused event; the board reconstruction still embeds and
      disposes correctly.

## 4. Responsive + scroll-safe layout

- [x] 4.1 Two-region layout (games list · transcript) that holds across window sizes with no horizontal
      overflow; the games list collapses on narrow widths; the transcript and any open drawer scroll
      independently.
- [x] 4.2 Tests/checks for layout integrity (no horizontal overflow; list collapse; independent scroll).

## 5. Verification and specs

- [x] 5.1 `pnpm` typecheck + tests + lint green for the dashboard (tsc clean; history+proxy 94/94, full dashboard 182; eslint clean). `/history` loads with zero console errors on the integrated branch.
- [ ] 5.2 Drive the live app via Playwright: pick a game from the list, read the whole game as a continuous
      transcript (agent moves, game states, user prompts, nested verdicts), restore/open-board from an
      inline action, and evaluate from the header drawer.
- [ ] 5.3 Sync `openspec/specs/` and archive the change.

## 6. Evaluation UX fixes

- [x] 6.1 Fix B — visually distinguish move-scope vs round/range/game-scope verdicts in the transcript's
      nested eval sub-tree: each verdict carries a `history-eval-scope-{seq}` scope chip ("Move",
      "Round N", "Range", "Whole game") derived from the verdict's `scope` + `round_span`, so a
      round/whole-game verdict no longer reads as grading one move. Test asserts a round-scope verdict's
      scope label differs from a move-scope one. (Fix A — drawer stream persistence — dropped: a
      forthcoming evaluations-queue change owns that; the Evaluate drawer keeps its current behavior.)
