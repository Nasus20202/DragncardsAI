## 1. Service Scaffold and Configuration

- [x] 1.1 Create `services/eval-service/` with FastAPI app structure, package metadata, Dockerfile, and local test configuration, mirroring `services/history-service/`.
- [x] 1.2 Add eval-service settings for the dedicated PostgreSQL URL, history-service base URL, Bifrost gateway URL, judge provider/model (required, no default), judge Bifrost identity reference, retry/attempt limits, concurrency caps, and per-evaluation token budget, all with secret-free defaults.
- [x] 1.3 Add health and readiness endpoints reporting API, PostgreSQL, history-service, and Bifrost readiness without exposing secrets.
- [x] 1.4 Add unit tests for settings validation and health/readiness responses.

## 2. History Envelope + Replay (history-event-store delta)

- [x] 2.1 Extend the history-service envelope allowed-actor set to accept `evaluator` in addition to `agent` and `game-service`, rejecting any other actor as before.
- [x] 2.2 Ensure `evaluator` events are excluded from restore forward-replay (advisory, like `agent` events), so verdicts are never re-applied as game mutations.
- [x] 2.3 Add unit tests proving `evaluator` envelopes are accepted (and unknown actors rejected) and that `evaluator` events are skipped by restore replay.

## 3. Evaluation Bookkeeping and Idempotency

- [x] 3.1 Define eval-service models/migrations for an evaluated-target record keyed by unique `(game_id, target_seq, scope)`, plus attempt counts and skip/error outcomes, in the dedicated eval PostgreSQL.
- [x] 3.2 Implement a claim-then-finalize idempotency path (`ON CONFLICT DO NOTHING` / `SET NX` claim finalized on success) so a target is evaluated at most once across concurrent replicas.
- [x] 3.3 Add PostgreSQL-backed unit tests proving a target is evaluated at most once and that concurrent claims for the same target resolve to a single evaluation.

## 4. On-Demand Evaluation Request API

- [x] 4.1 Implement the evaluation request API (e.g. `POST /games/{game_id}/evaluations`) accepting a target selection — specific move `seq`s, round(s), a `seq` range, scope `move`/`round`, or whole game (plus an optional `force` re-evaluate flag) — that expands the selection into concrete targets, applies the idempotency claim, and dispatches them to evaluation (sync or via an internal worker).
- [x] 4.2 Implement a request status/results endpoint reporting per-target state (pending/completed/skipped/failed) and the resulting verdicts.
- [x] 4.3 Add tests proving a request evaluates only the selected targets, that unselected moves/rounds are not evaluated, that a repeated request is not re-evaluated without `force`, and that `force` produces a fresh verdict.

## 5. Judge Input Assembly

- [x] 5.1 Implement per-move input assembly that reads the target `agent` move event (action, reasoning/context, arguments) and correlates the nearest prior and resulting `game-service` state events from the history read API.
- [x] 5.2 Implement round-boundary detection from the round/phase field on `game-service` state events, with a terminal-status fallback to close the final round, and assemble the per-round input spanning the round's moves.
- [x] 5.3 Add unit tests for move-input correlation and round-boundary detection (including the terminal-status fallback and the boundary-undetected surfaced case).

## 6. Judge Integration with Dedicated Bifrost Identity

- [x] 6.1 Add a dedicated `eval-judge` Bifrost virtual key/provider entry in `services/bifrost/config.json` (env-backed, secret-free defaults) distinct from the game-playing keys.
- [x] 6.2 Implement a fresh, stateless judge invocation through Bifrost under the dedicated identity, with a structured evaluation prompt (rubric + assembled inputs + agent reasoning) that MAY load the Marvel Champions rules skills; model/provider configurable.
- [x] 6.3 Parse the judge response into a structured verdict (per-criterion scores, overall score, rationale, flags, evaluator metadata).
- [x] 6.4 Add unit tests proving judge calls route under the dedicated identity (not the game-playing identity), run in a fresh session, and produce a structured verdict from a stubbed Bifrost response.

## 7. Per-Move and Per-Round Evaluation

- [x] 7.1 Implement per-move evaluation: for an `agent` move target, assemble input, invoke the judge, and produce a `scope=move` verdict targeting the move's `seq`.
- [x] 7.2 Implement per-round evaluation: when a round closes, assemble the round input, invoke the judge, and produce a `scope=round` verdict targeting the closing `seq` with `round_span`.
- [x] 7.3 Implement concurrency/token-budget cost controls (per-game and global concurrency caps; per-evaluation token budget) for processing requested targets.
- [x] 7.4 Add integration tests proving a request over a recorded game produces one move verdict per selected move and one round verdict per selected/closed round.

## 8. Evaluator-Event Write-Back

- [x] 8.1 Implement write-back of each verdict to the history-service HTTP ingest endpoint as an envelope with actor `evaluator` and the documented verdict payload, using `idempotency_key = hash(game_id, target_seq, scope, evaluator_version)`.
- [x] 8.2 Finalize the evaluated-target bookkeeping record only after a successful write-back.
- [x] 8.3 Add integration tests proving a verdict is ingested onto the same game timeline as an `evaluator` event referencing the correct `target_seq`/`round_span`, and that a duplicate write-back is stored once.

## 9. Failure Isolation and Cost Controls

- [x] 9.1 Implement retry-with-backoff up to the configured attempt limit, then skip-and-continue per target (record skip/error outcome in the request status) so one failing target never blocks the rest of a request.
- [x] 9.2 Verify, by construction and test, that a failing or slow judge never blocks or slows history ingestion or game play (eval reads committed copies and only writes advisory events).
- [x] 9.3 Add integration tests proving a failing judge results in a skipped target without blocking ingestion, and that ingestion/play proceed unaffected while the judge is down.

## 10. Dashboard Surfacing (game-history-ui delta)

- [ ] 10.1 Render `evaluator` events on the existing game history timeline, visually distinct from `agent` and `game-service` events, anchored to the move/round they grade. (Done in feat/dashboard-eval-scores.)
- [ ] 10.2 Show the verdict detail (per-criterion scores, overall score, rationale, flags) when an evaluator event is selected. (Done in feat/dashboard-eval-scores.)
- [ ] 10.3 Add a control to select which targets (moves/rounds/range/whole game) to evaluate and submit the request to the eval-service, surfacing per-target request status and the resulting verdicts.
- [ ] 10.4 Add a dashboard test/Playwright check proving the user can select targets, trigger evaluation, and see evaluator events/scores appear on the timeline against the graded move/round.

## 11. Infrastructure and Compose (infrastructure delta)

- [x] 11.1 Add the `eval-service` (and its dedicated PostgreSQL) to Docker Compose with secret-free defaults and the dedicated Bifrost judge identity wired via environment.
- [x] 11.2 Verify the eval-service connects to its own isolated database (not history's or orchestrator's) and that the Bifrost judge key is external (not committed).
- [x] 11.3 Add an end-to-end integration test that, given a recorded game, submits an on-demand evaluation request for selected targets and asserts evaluator events appear on the timeline with valid verdicts under the dedicated Bifrost identity.

## 12. Review Fixes

- [x] 12.1 Make worker target claims exclusive across replicas: the worker atomically claims pending targets into `running` (`SELECT ... FOR UPDATE SKIP LOCKED` on Postgres, conditional `UPDATE ... WHERE status='pending'` otherwise) and only evaluates rows it won; an at-most-once integration test runs two concurrent drains and asserts each target is judged exactly once.
- [x] 12.2 Make `force` re-claim atomic with an in-flight worker: the conflict check and reset-to-`pending` run in a single transaction, and the worker's terminal transitions are conditional on the row still being `running`, so a force reset is never clobbered.
- [x] 12.3 Bound selection size: a configurable `eval_max_targets_per_request` (default 200) rejects over-cap expansions with HTTP 400, plus Pydantic caps on `seqs`/`rounds` length and `seq_range` span.
- [x] 12.4 Round scope maps a selected mid-round seq to its containing round rather than 400ing; only seqs outside every detectable round error.
- [x] 12.5 Remove the dead "list evaluations" path (endpoint, schemas, repository method, `created_count`/`skipped_count`/`attempts` columns, dashboard client + types) and dead `_as_utc`/`increment_attempts`/`ping_database` helpers.
- [x] 12.6 Honor `BifrostError.retryable` (non-retryable judge errors fail fast), add `Repository.ping()` for readiness, aggregate request status into `pending`/`completed`/`partial`/`failed`, tighten JSON-fence parsing with a proper fence regex, and dedup `readJson` into a shared module.
