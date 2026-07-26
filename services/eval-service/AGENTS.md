# Eval Service Agent Guide

Read this file before making changes in `services/eval-service/`.

## Scope

These instructions apply to the eval-service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Language**: Python 3.14 with `uv`
- **Framework**: FastAPI (lifespan app + background asyncio worker)
- **Database**: dedicated PostgreSQL for evaluation requests, targets, idempotency
- **LLM gateway**: Bifrost, under a dedicated `eval-judge` identity
- **Testing**: pytest async (sqlite for unit, real Postgres for integration)

## Core Concepts

### On-demand, user-selected evaluation

There is NO automatic per-event evaluation. A user `POST`s a selection of
moves/rounds; the eval-service expands it into concrete targets, claims them
idempotently, and a background worker grades each one.

### Idempotency

Targets dedupe on UNIQUE `(game_id, target_seq, scope)` via `INSERT ... ON
CONFLICT DO NOTHING` (claim-then-finalize). A target is evaluated at most once
across concurrent workers; `force` resets the row to re-evaluate.

### Isolated judge

Each evaluation is a fresh, stateless Bifrost chat completion under the dedicated
`eval-judge` virtual key — never the game-playing agent's session/identity.
`EVAL_JUDGE_MODEL` is required; with none configured the service refuses to
evaluate with a clear error (and readiness reports `degraded`).

### Write-back and failure isolation

Verdicts are written back to history as `evaluator` events. The bookkeeping row
is finalized to `completed` only AFTER a successful write-back. A judge call is
retried with backoff to the attempt limit, then the target is skipped — one
failing target never blocks the rest, and eval never blocks ingestion or play.

## Working Rules

- Use `uv run` for all commands inside the service directory.
- Never store state in memory: all durable state is in this service's own Postgres.
- Health/readiness must never echo secrets.
- `except A, B:` paren-free tuple-catch is valid PEP 758 on 3.14 — do not add parens.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + stubs)
uv run pytest tests/integration -v   # Integration (needs Postgres)
uv run black src tests               # Format
```
