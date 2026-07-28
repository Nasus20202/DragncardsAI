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
`eval-judge` key — never the game-playing agent's session/identity.
`EVAL_JUDGE_MODEL` is required; with none configured the service refuses to
evaluate with a clear error (and readiness reports `degraded`).

The identity is pinned by the `x-bf-api-key: eval-judge` header, NOT by the
`Authorization` bearer (which Bifrost ignores for key selection). Every provider
in `services/bifrost/config.json` defines an `eval-judge` key entry at
`weight: 0.0` from its own `EVAL_JUDGE_<PROVIDER>_API_KEY`, so any provider can
judge under its own budget. Never make the judge fall back to a game-playing key
implicitly: a missing judge key must surface as a `degraded` readiness
`judge_key.status` and as the gateway's explicit error on the target. See
[Judge identity](README.md#judge-identity).

### The judge prompt is projected and windowed

Recorded `game_state` events carry the RAW DragnCards room state (~450 KB on real
games, ~half of it the internal `deltas` log). NEVER put a recorded state straight
into a prompt: project it through `judge/state_view.py`, which reduces it to the
same view the playing agent saw and collapses face-down cards and deck contents to
`HIDDEN` counts. `EVAL_JUDGE_MAX_STATE_CHARS` is a backstop, not the mechanism.

A move prompt carries a configurable WINDOW of neighbouring agent moves, not the
whole timeline — the states already summarise the past, while the neighbours show
that a tool call is one step of a multi-call play. See
[What the judge is sent](README.md#what-the-judge-is-sent).

### Round boundaries follow post-action state, and rounds are 1-based

`judge/assembly.py` derives round spans from the raw `roundNumber` on
`game-service` state events. Two DragnCards facts govern it and are easy to get
backwards:

- A `game-service` event embeds the state AFTER its action was applied, so the
  event whose state first reports a NEW `roundNumber` is the event that CLOSED the
  previous round — it is that round's last seq, and the next round starts after it.
- `roundNumber` counts COMPLETED rounds (it is 0 for the whole first round of
  play), so every round number this service reports or accepts is
  `round_of_play()`, i.e. `roundNumber + 1`. Never surface the raw counter to a
  judge or a user; the History UI uses the same convention.

Changing boundary detection changes what a round roll-up is graded on, so it
changes evaluation results: bump `EVALUATOR_VERSION` and state in the spec why
older verdicts are no longer comparable, rather than silently re-scoping them.
See [Round boundaries](README.md#round-boundaries).

### Non-strategic actions are skipped, never silently

`judge/actions.py` classifies recorded actions. The line is whether the action
commits game state a player could get wrong — searching for a card cannot be a
wrong decision, taking one into hand can be — NOT whether the tool reads or
writes. Anything the taxonomy does not recognise is EVALUATED; only widen the skip
list deliberately, because over-skipping degrades evaluation quality invisibly. A
skipped target is recorded as `skipped` with its reason through the same
`mark_skipped` channel a judge failure uses.

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
