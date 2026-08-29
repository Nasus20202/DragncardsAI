## 1. Exercise the worker through its HTTP boundary

- [x] 1.1 Extend the existing in-process integration fake-provider harness so a deterministic truncating response sequence and continuation settings can be supplied without reading ambient provider configuration; verify with the focused agent-orchestrator integration test collection.
- [x] 1.2 Add an HTTP API regression for a repeated truncation that reaches the configured continuation cap, asserting a completed job, the accumulated output, and exactly one persisted continuation marker; verify with `uv run pytest tests/integration/test_api_jobs.py -k truncated_turn -q`.
- [x] 1.3 Add an HTTP API regression with `auto_continue_truncated_turns` disabled, asserting the first truncated segment completes without a continuation marker; verify with the same focused pytest command.

## 2. Exercise dashboard rendering in Chromium

- [x] 2.1 Add a dedicated `services/smoketest` Playwright scenario with controlled orchestrator responses for a completed parent job and child job, including `model_output`, `turn_continued`, and `completion` events; `pnpm typecheck` passes and unhandled API routes throw from the route handler.
- [x] 2.2 Drive the real dashboard Play workspace in Chromium, assert the continuation seam between parent output segments, expand the subagent list, open the child output modal, and assert the seam and segments there; `DASHBOARD_SMOKE_BASE_URL=http://localhost:3001 pnpm exec playwright test tests/turn-continuation-smoke.spec.ts --project=chromium` passes (1 test).

## 3. Record runtime verification honestly

- [x] 3.1 Attempt to start the merged-code infrastructure and application stack after initializing required submodules; the three coupled DragnCards images built, but startup stopped because the existing `dragncardsai-dragncards-postgres-1` already occupied host port `5440`, so a second `wt-dra55` Compose project could not bind it. The source dashboard was started separately on port `3001` for the browser check.
- [x] 3.2 Run the focused fake-provider HTTP regressions and the focused browser scenario where their required dependencies are available; `uv run pytest tests/integration/test_api_jobs.py -k 'truncated_turn' -q` passes (3 tests), and the route-intercepted Chromium smoke passes (1 test). These are deterministic in-process/route-intercepted proofs, not a claim that a deployed fake-provider stack ran.
- [x] 3.3 Confirm the archived DRA-45 context-guard rebase note is satisfied by the existing `estimate_request` call site, with no production edit needed; verify by inspecting the current call site and its existing refactor commit.
