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

### A move is judged in the context of its round

A move prompt carries the agent moves of the graded move's OWN ROUND, on BOTH
sides of it. The round is the window: never reach into an adjacent round (a
different turn on a different board), never stop inside the round (that hides the
rest of the play). A Marvel Champions play is normally 2-4 tool calls and each one
is its own recorded event, so grading a call in isolation scores a good play down
once per call — the defect DRA-10 was filed for. The rubric therefore also tells
the judge to grade an action as its step within the play its round reveals.

`EVAL_JUDGE_MOVE_CONTEXT_BEFORE`/`_AFTER` are BACKSTOPS against a pathological
round, not the window. Do not shrink them to save payload: this supersedes DRA-7's
narrow fixed-count window on the explicit ruling that accuracy takes priority over
prompt size. DRA-7's other two mechanisms — the state projection and the
non-strategic skip taxonomy — stay exactly as they are.

The skip taxonomy does NOT apply to context. An action skipped as a target still
appears as context, because it shows intent even when it holds no gradeable
decision. See [What the judge is sent](README.md#what-the-judge-is-sent).

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

A verdict therefore records TWO different numbers about its round and they are not
interchangeable: `round_span` is the `[from_seq, to_seq]` SEQ span it graded, and
`round_number` is the round of PLAY it is (round scope only). Name a round from
`round_number`, never from the span — reading the span as a round range labelled a
real game's first round "Rounds 1-63" (DRA-25). Keep `round_of_play()` the single
conversion there is: put the converted number on the payload instead of leaving a
client to re-derive it from seqs.

### Non-strategic actions are skipped, never silently

`judge/actions.py` classifies recorded actions. The line is whether the action
commits game state a player could get wrong — searching for a card cannot be a
wrong decision, taking one into hand can be — NOT whether the tool reads or
writes. Anything the taxonomy does not recognise is EVALUATED; only widen the skip
list deliberately, because over-skipping degrades evaluation quality invisibly. A
skipped target is recorded as `skipped` with its reason. `skipped` means "there
was no decision to grade here" and is reserved for exactly that: an ERROR is
recorded as `failed`, never as a skip, so a client can tell the two apart.

### Write-back and failure isolation

Verdicts are written back to history as `evaluator` events. The bookkeeping row
is finalized to `completed` only AFTER a successful write-back. A judge call is
retried with backoff to the attempt limit, then the target is marked `failed`
with the reason — one failing target never blocks the rest, and eval never blocks
ingestion or play.

### Errors are reported live, not only at the end

Every failed judge attempt is written to the target row (`error`, while the row
stays `running`) and pushed through the worker's live sink, so a retry storm or a
definitive misconfiguration is visible DURING the run instead of only in the final
status. Never hold error detail in the worker: a poller has to be able to read it,
which means Postgres.

All error text passes through `error_detail.sanitize_error_detail` at the
repository boundary (`mark_failed` / `mark_skipped` / `record_attempt_error`) —
gateway messages can embed an `Authorization` header or a provider body echoing
the whole prompt. Record errors through those methods only; never write the
`error` column directly.

### Concurrency lives in the claim, not in the process

Multiple targets are evaluated in parallel, and both caps
(`EVAL_PER_GAME_CONCURRENCY`, `EVAL_GLOBAL_CONCURRENCY`) are enforced inside
`Repository.claim_pending_targets`: it counts the rows already `running` and takes
only the remaining capacity. Do NOT reintroduce a semaphore, a per-game dict, or
any in-process registry of running work — that is banned state, it leaks, and it
does not hold for a second replica. `EvaluationWorker.drain_once` reports PROGRESS
rather than rows touched, so a cycle where every roll-up merely re-deferred is
idle and the worker waits instead of hot-looping on the database.

### Observability

Telemetry comes from `dragncards_common.telemetry`; `eval_service/telemetry.py`
only binds `DEFAULT_SERVICE_NAME = "eval-service"` to it. Three edges are wired
and all three must stay wired — this service shipped with its `OTEL_*` variables
set in compose and no instrumentation at all (DRA-23), which exported nothing:

- `main.py` calls `setup_telemetry()` before the app is built.
- `runtime/app.py` calls `instrument_fastapi_app(app)` and `shutdown_telemetry()`.
- `storage/db.py` calls `instrument_sqlalchemy_engine(engine)` in `create_engine`.

`runtime/worker.py` opens one `eval.evaluate_target` span per graded target: the
judge lifecycle is where the latency lives and generic instrumentation cannot
explain it. The span records the outcome (`evaluated`, `not_configured`,
`cancelled`, `failed`) and nothing further about it.

This service handles the two most sensitive payloads in the repository — the judge
prompt and the recorded game state it is assembled from. NEVER attach either, a
judge response, or a gateway error message (which can echo a whole request body)
to a span attribute. Error detail belongs on the target row via
`sanitize_error_detail`; the span gets an outcome word. The permitted attribute
keys are pinned in `tests/unit/test_telemetry.py`.

## Working Rules

- Use `uv run` for all commands inside the service directory.
- Never store state in memory: all durable state is in this service's own Postgres.
- Health/readiness must never echo secrets, and neither must recorded error text.
- `except A, B:` paren-free tuple-catch is valid PEP 758 on 3.14 — do not add parens.

## Testing

```bash
uv run pytest tests/unit -q          # Unit tests (sqlite + stubs)
uv run pytest tests/integration -v   # Integration (needs Postgres)
uv run black src tests               # Format
```
