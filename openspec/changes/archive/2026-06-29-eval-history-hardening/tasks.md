## 1. eval-service correctness

- [x] 1.1 Make the verdict idempotency key incorporate a stable hash of the resolved judge config (model/provider/prompt_override/skills/reasoning) so a forced re-eval with a different judge is recorded distinctly; identical re-evals still dedupe.
- [x] 1.2 Cancel-safe write-back: re-check the target is still `running` immediately before writing the verdict to history.
- [x] 1.3 Cap/truncate judge input (`EVAL_JUDGE_MAX_STATE_CHARS`, `EVAL_JUDGE_MAX_ROUND_MOVES`); truncate the largest per-event state JSON and log when truncation occurs.
- [x] 1.4 Tests for idempotency-key config sensitivity, cancel-before-write-back, and input truncation.

## 2. eval-service hardening

- [x] 2.1 Restrict CORS from `*` to a configurable allowlist (`EVAL_CORS_ALLOW_ORIGINS`, default local dashboard origins).
- [x] 2.2 Validate `game_id` (`^[A-Za-z0-9_-]{1,64}$`) at the route boundary; url-encode `game_id` in `integrations/history.py` path construction.

## 3. history-service hardening

- [x] 3.1 Validate `game_id` at the route boundary (events, snapshots, restore, games/delete), preserving idempotent absent-id semantics.
- [x] 3.2 Url-encode outbound path params in `integrations/game_service.py`.
- [x] 3.3 Allowlist the replay `action_path` to the known endpoint shape; reject anything else.
- [x] 3.4 Tests for rejected malformed `game_id`, encoded path params, and rejected bogus `action_path`.

## 4. dashboard hardening + simplify

- [x] 4.1 Proxy: reject cross-site requests (Sec-Fetch-Site / Origin-host check) and strip inbound cookie/authorization/x-forwarded-* before forwarding; keep content-type. Test it.
- [x] 4.2 Share Play's provider/model reconciliation helpers (`isWorking`, `clampModelToProvider`) instead of the `judge-config.ts` duplicates.
- [x] 4.3 Extract `useEvaluationStream` hook + `EvaluationStatusList` from `evaluation-control.tsx`, preserving incremental refresh, cancel, poll fallback, and all `data-testid`s.

## 5. Verification

- [x] 5.1 Unit + integration green for all three services; dashboard typecheck + tests + lint green.
- [ ] 5.2 Live re-verify via Playwright: forced re-eval with a changed judge records a new verdict; cancel does not leave a stray verdict; a large-game eval no longer 400s on a small model.
- [ ] 5.3 Sync `openspec/specs/` and archive the change.
