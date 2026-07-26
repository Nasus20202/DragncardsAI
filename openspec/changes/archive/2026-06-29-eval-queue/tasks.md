## 1. eval-service cross-game listing

- [x] 1.1 `Repository.list_requests(limit, active_only)` — query evaluation requests over the
      eval Postgres ordered by `created_at` DESC, joined/aggregated with their targets; when
      `active_only`, restrict to requests with at least one non-terminal target. Bounded limit.
- [x] 1.2 `GET /evaluations` route returning a list of request summaries
      `{request_id, game_id, status, created_at, targets:[{scope, target_seq, round_span, status}]}`
      (overall status via the existing `request_status` helper). Query params `active` (bool,
      default false) and `limit` (int, default e.g. 50, hard-capped). No game_id in the path
      (cross-game); ordering newest-first.
- [x] 1.3 Tests: lists requests across multiple games newest-first; `active=true` filters out
      fully-terminal requests; `limit` is capped; empty store returns `[]`.

## 2. dashboard queue data layer

- [x] 2.1 `listEvaluations({active?, limit?})` in `features/history/lib/eval-api.ts` calling
      `GET /api/proxy/eval/evaluations`; extend the proxy path allowlist if needed.
- [x] 2.2 `useEvaluationQueue` hook: poll `listEvaluations` (~2s) while the queue panel is open
      OR any request is active; expose the request summaries, an active count, and
      `cancel(gameId, requestId)` (reusing `cancelEvaluation`). No in-memory persistence beyond
      the view cache.

## 3. dashboard persistent queue UI (History tab)

- [x] 3.1 Header control "Evaluations" with an active-count badge (`history-eval-queue-open`),
      always present in the History tab regardless of the selected game / Evaluate drawer.
- [x] 3.2 Standing queue panel/drawer (`history-eval-queue`) listing rows across all games:
      friendly game name (reuse the `gameNames` mapping) + scope label ("Move #seq" / "Round N"
      from round_span / "Range" / "Whole game") + status + progress + per-request **Cancel**
      (`history-eval-queue-cancel-{requestId}`, shown only while non-terminal); empty state
      (`history-eval-queue-empty`). Row testid `history-eval-queue-item-{requestId}`.
- [x] 3.3 Tests: queue lists requests from multiple games with correct scope labels; cancel
      calls `cancelEvaluation`; active-count badge reflects non-terminal requests; empty state.

## 4. dashboard Evaluate drawer → configure-and-submit-only

- [x] 4.1 Refactor the Evaluate drawer to configure scope + judge and submit only; on submit,
      enqueue the request, surface a brief "added to the queue" confirmation, and allow closing
      immediately. Remove the inline streaming/token/cancel UI from the drawer (it lives in the
      queue now). Keep the judge-config + scope-selection UI and all existing submit testids.
- [x] 4.2 Tests: submitting enqueues the request and it appears in the queue; closing the drawer
      after submit keeps the request running and visible/cancelable in the queue (the regression
      the user reported — no lost progress).

## 5. Verification and specs

- [ ] 5.1 eval-service unit + integration green; dashboard typecheck + tests + lint green.
- [ ] 5.2 Drive the live app via Playwright: submit a move, a round, and a whole-game evaluation;
      see all three in the persistent queue with distinct scope labels and live status; close the
      Evaluate drawer / switch games and confirm they persist; cancel one from the queue.
- [ ] 5.3 Sync `openspec/specs/` and archive the change.

## 6. Clear/delete evaluations

- [x] 6.1 `Repository.delete_request(request_id) -> bool` — delete a request and its targets in one
      transaction, returning whether it existed; and `Repository.delete_terminal_requests() -> int`
      — delete every request with NO non-terminal target (clear-all), returning the count, with the
      terminal filter expressed in SQL (the `list_requests` active subquery, negated).
- [x] 6.2 `DELETE /evaluations/{request_id}` (cross-game, not under `/games/{id}`): 404 if missing;
      **409** if the request still has a non-terminal target (a running request can only be
      cancelled, never cleared); 204 on success. Clearing removes only the eval-service queue
      tracking rows; recorded history verdicts are untouched.
- [x] 6.3 `POST /evaluations/clear` clears all fully-terminal requests and returns
      `{ "deleted_count": N }`; requests with a non-terminal target are left intact. (Chosen over an
      unbounded `DELETE /evaluations` collection.)
- [x] 6.4 eval-service tests: delete a terminal request (gone from the listing); delete a running
      request → 409 and it remains; delete missing → 404; clear-all removes only terminal requests,
      leaves active ones, and returns the count.
- [x] 6.5 dashboard data layer: `deleteEvaluation(requestId)` (`DELETE /api/proxy/eval/evaluations/
      {requestId}`) and `clearEvaluations()` (`POST /api/proxy/eval/evaluations/clear`); hook gains
      `remove(requestId)` and `clearTerminal()` (each refreshes after; a 409 surfaces as an error
      then refreshes), plus a `terminalCount`.
- [x] 6.6 dashboard queue UI: a per-row **Clear** shown ONLY for terminal requests
      (`history-eval-queue-clear-{requestId}`) while non-terminal rows still show Cancel; a header
      **Clear all** (`history-eval-queue-clear-all`) clearing terminal requests, disabled when none
      are terminal. Reuses the `eval-queue.ts` terminal logic.
- [x] 6.7 dashboard tests: a terminal row shows Clear and calls `deleteEvaluation`; a running row
      shows Cancel (not Clear); Clear all calls `clearEvaluations`; Clear all is disabled with no
      terminal requests.
