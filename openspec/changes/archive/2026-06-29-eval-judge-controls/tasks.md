## 1. eval-service — per-evaluation judge config

- [x] 1.1 Extend the evaluation request schema with an optional `judge` object (provider_id, model_name, reasoning{enabled,effort,max_tokens}, prompt_override, skills[]); validate fields and reject unknown skills with 400.
- [x] 1.2 Persist the effective judge config on the request/target rows so the async worker and the stream use it.
- [x] 1.3 Add a `SKILL_ROOTS` setting and resolve selected skill names to skill content for the judge prompt; honor reasoning/provider/model overrides via Bifrost, mirroring the orchestrator's reasoning mapping.
- [x] 1.4 Record the actual model/provider used on the verdict's evaluator metadata.
- [x] 1.5 Unit tests for config validation, skill resolution, default fallback, and verdict provenance.

## 2. eval-service — streaming + cancel

- [x] 2.1 Add a streaming Bifrost judge path (chunked/SSE) that yields incremental output and is cancellable.
- [x] 2.2 Add `GET /games/{game_id}/evaluations/{request_id}/stream` (SSE) emitting `status`, `token`, `verdict`, and `done` events with keepalives.
- [x] 2.3 Add `POST /games/{game_id}/evaluations/{request_id}/cancel` that marks non-terminal targets `cancelled` and aborts in-flight judge calls; add the `cancelled` terminal status and update the request-status aggregate.
- [x] 2.4 Tests: stream emits status+verdict for a stubbed judge; cancel transitions targets to `cancelled`, writes no verdict, and the stream closes.

## 3. history-service — list + delete

- [x] 3.1 Add `GET /games` returning games-with-history (game_id, event_count, first/last recorded_at) via a single grouped query.
- [x] 3.2 Add `DELETE /games/{game_id}` removing all events, snapshots, and per-game bookkeeping in one transaction; idempotent with zero counts when absent.
- [x] 3.3 Unit/integration tests for listing and deletion (including idempotent delete and that deletion removes events + snapshots).

## 4. dashboard — picker + delete

- [x] 4.1 Add a history-games client and source the history/eval game picker from `GET /api/proxy/history/games`, preserving `?game_id=` deep-linking.
- [x] 4.2 Add a delete-history control with a confirm dialog calling `DELETE /api/proxy/history/games/{game_id}`, clearing selection and refreshing the list on success.
- [x] 4.3 Tests for the picker source and the delete flow.

## 5. dashboard — judge config panel (Play parity)

- [x] 5.1 Add provider/model, reasoning (enabled/effort/max-tokens), custom prompt/rubric, and skills multiselect to the Evaluate control, reusing the Play provider/skill sources and dashboard defaults.
- [x] 5.2 Include the assembled `judge` object in the evaluation request, omitting empty fields.
- [x] 5.3 Tests for the config panel and request assembly.

## 6. dashboard — live status + cancel

- [x] 6.1 Consume the eval SSE stream via EventSource for live per-target status and incremental judge output, with a polling fallback.
- [x] 6.2 Add a Cancel button for in-flight requests calling the cancel endpoint; on `done`, reload history so new evaluator events render.
- [x] 6.3 Tests for live-status rendering and cancel.

## 7. Verification and specs

- [ ] 7.1 Run lint + unit/integration suites for eval-service, history-service, and dashboard.
- [ ] 7.2 Drive the live app via Playwright: pick a game-with-history, configure the judge, run an evaluation watching live status, cancel one, and delete a game's history.
- [ ] 7.3 Sync `openspec/specs/` and archive the change.
