## 1. Readable conversation (Play parity)

- [x] 1.1 Extract/reuse the Play transcript presentation (message bubbles, collapsible reasoning, tool-call/result cards) so it can render an arbitrary message array.
- [x] 1.2 In the history detail, map an `agent_move` event's `conversation_context` (OpenAI-format messages incl. `tool_calls` and `tool` results) to that presentation and render it instead of raw JSON; keep intended action / arguments / reasoning summarized above it.
- [x] 1.3 Tests for message→transcript mapping and rendering (incl. tool calls + results).

## 2. Board at the selected event (dashboard)

- [x] 2.1 Add an "Open board at this event" control that restores the selected `seq` into a fresh EPHEMERAL session (`mode: "new"`, `ephemeral: true`), resolves the new session's `room_slug` (game-service `GET /games`), and embeds it via `DragnCardsIframe` so the user can click around the reconstructed board. Only one reconstruction is live at a time (dispose the previous before opening a new one).
- [x] 2.2 Tear the ephemeral reconstruction down on close: on component unmount / deselect / opening a different moment, and on tab close (`pagehide`/`visibilitychange` via `fetch keepalive`) — call game-service `DELETE /games/{session_id}`. The ephemeral session is non-emitting, so no history cleanup is needed; a server-side TTL reaper is the safety net for lost connections, so client teardown is best-effort.
- [x] 2.3 Tests for open (restore with `ephemeral:true` → resolve → embed) and teardown (session DELETE fires on unmount / explicit close / pagehide; no history DELETE).

## 5. Ephemeral reconstruction lifecycle (backend safety net)

- [x] 5.1 history-service restore: accept an `ephemeral` flag and pass it through to branch-session creation, distinct from a kept `mode:"new"` session.
- [x] 5.2 game-service: tag ephemeral reconstruction sessions (created_at + ephemeral) in the session store; the history emitter SHALL skip ephemeral sessions (no events emitted).
- [x] 5.3 game-service: a background reaper deletes ephemeral sessions and their DragnCards rooms once older than a configurable TTL, so a lost-connection / crashed client cannot leak a session or room.
- [x] 5.4 Tests: ephemeral sessions emit no history; the reaper deletes an expired ephemeral session+room; a kept `mode:"new"` session is never reaped.

## 3. Responsive layout polish

- [x] 3.1 Restructure the history page into a responsive, scroll-safe layout (timeline · detail/board · controls) that does not clip or overflow at any window size, including the large judge-config panel.
- [x] 3.2 Tests/checks for layout integrity (no horizontal overflow; controls and detail independently reachable).

## 6. Reconstruction correctness (full-state base)

- [x] 6.1 game-service: record the session `plugin_name` slug on every `game_state` event payload so a branchable restore can materialize a session even when no snapshot exists yet (short games).
- [x] 6.2 history-service: resolve the branch `plugin_name` from snapshot → any snapshot → earliest `game_state` event, so reconstruction works without a periodic snapshot.
- [x] 6.3 history-service: load the FULL state embedded in the nearest `game_state` event as the reconstruction base (densest available), instead of replaying sparse actions — setup actions (deck loads) are not recorded as replayable, so action-replay produced an empty board.
- [x] 6.4 history-service: ephemeral (view-only) reconstructions skip the agent-context restore (no orchestrator session created); fix `conversation_context` to be sent as a flat message list (the orchestrator restore endpoint requires a list, not a wrapped dict).
- [x] 6.5 Tests: full-state base loads cards without replay; plugin_name sourced from state event; ephemeral skips agent-context; non-ephemeral still restores it.

## 7. Evaluation UI refinements

- [x] 7.1 Move Evaluate out of the per-move controls into a game-level header button + side drawer (it can target the whole game, not just the selected move).
- [x] 7.2 Surface each move's verdict on the timeline as soon as it lands (refresh history on every `verdict` SSE event), not only when the whole request finishes.
- [x] 7.3 Game picker shows a friendly session name (orchestrator `metadata.game_id` → name), falling back to the game id.
- [x] 7.4 Tests: drawer opens from header and hosts the eval form; eval flow opens the drawer first; picker name mapping.
- [x] 7.5 History auto-refreshes (games list, friendly names, selected timeline) on tab focus/visibility and a slow poll while visible, so a game played in another tab appears without a manual reload.
- [x] 7.6 Drop the "Restore point" snapshot chip from the timeline (and its dead `snapshotSeqs` prop) — periodic snapshots are an internal reconstruction detail, not a user-facing marker; restore remains available per-event via the controls column.

## 8. Follow-ups (from review trio — not blocking this change)

- [ ] 8.1 eval-service: include the judge config (model/provider/prompt/skills/reasoning) in the verdict idempotency key, so a forced re-evaluation with a different judge is not silently dropped by history dedup (review: HIGH).
- [ ] 8.2 eval-service: register the in-flight task before the claim transition (or re-check `running` before write-back) to close the cancel-before-register race (review: MEDIUM).
- [ ] 8.3 eval-service: cap/truncate the judge input (full state JSON) so smaller-context models don't 400 on large prompts (review: MEDIUM; observed live with `laguna:free`).
- [ ] 8.4 Defense-in-depth: validate `game_id` with a strict pattern + URL-encode path params in service-to-service calls; restrict eval-service CORS; proxy origin/method checks (review: security MEDIUM).
- [ ] 8.5 Simplifications: share Play's provider/model reconciliation + field wrappers with the judge config; split `evaluation-control.tsx`; drop dead `_default_config`/`get_existing_target` (review: simplify).
- [ ] 8.6 Storage: consider delta-based `game_state` events + periodic full snapshots instead of full state on every event (storage optimization).

## 4. Verification and specs

- [x] 4.1 `pnpm test` / lint / typecheck / build green.
- [x] 4.2 Drive the live app via Playwright: recorded game selected, move read as a transcript, board reconstructed at an event (with full card state) and deleted on close, server reaper reclaims an abandoned ephemeral session, whole-game evaluation streamed + cancelled, per-move verdict surfaced.
- [ ] 4.3 Sync `openspec/specs/` and archive the change.
