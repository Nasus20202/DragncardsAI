## Why

The code-review / security-review / simplify pass over the evaluation + history work surfaced correctness, robustness, and defense-in-depth gaps that were deferred while the UI iterated. This change closes them: a forced re-evaluation with a different judge is currently dropped by history dedup; a cancel can race a verdict write-back; the judge prompt is unbounded (small-context models 400 on large games); and several service endpoints accept unvalidated `game_id` interpolated into internal URLs.

## What Changes

- **eval-service** SHALL make the verdict idempotency key config-aware so a forced re-evaluation with a different judge (model/provider/prompt/skills/reasoning) is recorded distinctly rather than deduped away, while identical re-evals still dedupe.
- **eval-service** SHALL not write a verdict for a target that was cancelled before its task registered (cancel-safe write-back).
- **eval-service** SHALL cap/truncate the judge input so large games do not exceed small model context windows, logging when truncation occurs.
- **eval-service** SHALL restrict CORS to a configurable allowlist and validate `game_id` at the route boundary; service-to-service URLs SHALL url-encode path params.
- **history-service** SHALL validate `game_id` at the route boundary, url-encode outbound path params, and allowlist the replay `action_path`.
- **dashboard** SHALL reject cross-site proxy requests and strip browser credential headers before forwarding to trusted upstreams; and SHALL share Play's provider/model reconciliation helpers and split the oversized evaluation control.

## Capabilities

### Modified Capabilities

- `agent-move-evaluation`: config-aware verdict idempotency, cancel-safe write-back, bounded judge input, and endpoint hardening (CORS allowlist, validated `game_id`, encoded path params).
- `history-event-store`: validated `game_id`, url-encoded service-call path params, and an allowlisted replay `action_path`.

## Impact

- eval-service, history-service, dashboard. New config: eval `EVAL_JUDGE_MAX_INPUT_CHARS` (+/or max-events cap), `EVAL_CORS_ALLOW_ORIGINS`. No schema migrations. The idempotency-key change makes forced re-evals with a changed judge produce new history events (intended). Dashboard proxy now rejects cross-site requests (same-origin usage unaffected).
