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

### Rules skills are inlined; their references are selected, never fetched

The judge is a SINGLE-SHOT completion. `BifrostJudgeClient` sends
`{model, messages, max_tokens}` with no `tools` key, `Evaluator._call_judge` makes
one call per attempt, and `parse_verdict` demands one JSON object. There is no tool
loop, so `load_skill` is not available to the judge and adding it means building
one — a provider-loop change, not a prompt change.

Selected skills' `SKILL.md` is inlined. Their reference files are selected
explicitly, as `"<skill-name>/<path>.md"` entries in `judge.skill_references`, and
inlined the same way. Three invariants hold that together, and breaking any of them
is a regression:

- **A config with no references produces a byte-identical prompt.** Everything new
  in `_system_content` is gated so the reference-free branch emits exactly what it
  emitted before, for the same reason the mode note is (see below).
  `ResolvedJudgeConfig.to_json()` OMITS `skill_references` when empty, which keeps
  `judge_config_digest` — and so every already-recorded idempotency key — unchanged.
  Emitting `[]` unconditionally would silently un-dedupe every stored verdict.
- **Reference content is never truncated.** State is clipped because a clipped
  board is still a board; a clipped rules reference reads to the judge exactly like
  a complete one. Over budget is a 400, raised in `resolve_judge_config` before any
  target is enqueued.
- **What bounds a reference selection is the context window.** There is no count
  limit; `MAX_SKILL_REFERENCES` (1,000) is a request-body guard, not a policy — a
  count measures nothing when the corpus spans a 20x size range.
  `judge/reference_budget.py` derives the size budget from
  `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` less the WORST of the three scope reserves
  (move, round, game hold different things; summing them reserves for a prompt
  that cannot exist) and the `SKILL.md` the same request selects. Do not
  reintroduce a fixed number: the derivation exists so "select all" works whenever
  it physically can, and refuses legibly when it cannot.
  `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` only ever *lowers* the derived budget —
  raising a character cap above the window bought a provider error, not capacity.
  (Skill `SKILL.md` selections are charged to the budget but are not themselves
  gated by it; `MAX_SKILLS` = 32 against ~91k chars of shipped skills is why.)
- **A new repeated prompt element needs a cap AND a reserve term.** The budget is
  only sound while the prompt honours what it reserves against, so anything
  rendered per move, per round or per child verdict must be bounded in count and
  size and charged in `reference_budget.py`. A move's `arguments` are the one
  deliberate exception: legality is judged on them, so they are projected in
  `MOVE_BLOCK_OVERHEAD_CHARS` rather than clipped.
- **The refusal message is load-bearing.** The skills catalogue reports reference
  *names* only, so the dashboard cannot show sizes and its "select all" can
  produce a selection the server refuses. The 400 is the only place the user
  learns why, so it carries the whole arithmetic. Do not shorten it.
- **A reference path is caller-supplied and stays inside its own skill.** All the
  rules live in `judge/skill_resources.py` and nowhere else. Every refusal raises
  the SAME message via `unresolvable()`, so the error cannot be used to probe the
  filesystem — do not add a more helpful one.

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

### A move is `is_agent_move(event)`, never `actor == "agent"`

`judge/events.py` owns the one predicate that decides whether a recorded event is a
play. Use it anywhere a move is selected, counted, attributed, spanned or graded.

The `agent` actor means "the agent-orchestrator produced this", not "the agent
played this". history-service pins `actor` to a fixed `Literal`
(`agent`/`game-service`/`evaluator`/`user`), so every new orchestrator concern
arrives as a new **event type** under that same actor — `illegal_action` is the
first. `actor == "agent"` is therefore a test that silently widens over time, and
each of the nine places that once used it was one new event type away from grading a
non-move as a play, attributing it to a seat, counting it into a round's move total,
and shifting a round span. `AGENT_MOVE_EVENT_TYPES` is an **allowlist**, so the next
event type the orchestrator adds is excluded by default rather than graded by
accident. Add to it deliberately; never invert it into a denylist.

### The judge is told the orchestration mode, and chat must not move

`MoveInput`/`RoundInput`/`GameInput` carry `session_mode`, read off the span's agent
events with `chat` as the default, so a game recorded before the mode existed reads
as chat. When it is `orchestrated` the projection states that each seat was a
separate agent holding its own context and its own persona, so the judge does not
mark a seat down for information it could not have seen.

**Every mode-dependent addition to a prompt must render as the empty string in chat
mode.** A chat projection has to stay byte-identical to what it was before
orchestrated mode existed, or verdicts stop being comparable across the change.
`tests/unit/test_judge_session_mode.py` pins the chat prompts against literal
expected strings captured from the pre-change code — do not regenerate those
literals from the current implementation, which is the one thing that would make the
test vacuous.

### Illegal-action findings are evidence, not verdicts

A round's `illegal_action` findings are collected onto `RoundInput` and rendered
naming the seat, the violation, and whether it is resolved or still open. The point
is that the judge no longer has to re-derive a violation the orchestrator already
established from game state — but a finding is one input to a score, not the score,
and the prompt says so. Keep it that way: a round with one corrected slip is not
automatically a zero. A finding with no named violation is dropped rather than shown,
because "something was wrong" only invites the judge to hunt for a fault to match,
and an unrecognised `status` reads as `open` — the conservative direction, since
treating an unfamiliar state as resolved would quietly retire a finding that may
still stand.

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

On PostgreSQL the claim transaction takes `pg_advisory_xact_lock` before it counts
the `running` rows. That count is what the cap is computed from, and it was
unlocked: under READ COMMITTED two replicas claiming at once each read the
pre-claim count and each spent the same capacity, so the global cap overshot by
the replica count. Keep the lock key a single shared constant — claimers that
contend on different keys do not serialize at all. SQLite already serializes
writers, so the lock is skipped there, exactly as `FOR UPDATE SKIP LOCKED` is.
Games already at their per-game cap are excluded in the candidate SELECT, BEFORE
the `LIMIT` window is taken; filtering them in Python afterwards let one game's
backlog fill the whole window and starve every other game. `ORDER BY created_at,
id` must stay as it is — it is what offers a cascade's move targets before the
roll-ups that depend on them.

**`run_forever` refills continuously; `self._tasks` is NOT the bound.** The loop
holds the tasks it is awaiting and wakes on `FIRST_COMPLETED`, re-claiming into a
freed slot at once rather than awaiting a whole batch (which made every slot wait
for the slowest target of its batch). Something has to hold an `asyncio.Task` to
await it, and that dict is only that — plus the id set the heartbeat needs. It is
NOT a semaphore, NOT a per-game registry, and must never grow into one. The test
to apply when reading or changing it: *if this set were emptied right now, would
the cap still hold?* It would, because capacity is re-read from the `running` rows
inside the claiming transaction, which is also why a second replica that has never
seen these tasks is bounded identically. Completions are harvested in bulk per
wake so one claim covers every freed slot — refilling one slot at a time would
multiply `list_all_events` round trips to history-service by the target count.

### The claim epoch, the lease, and the heartbeat

`evaluated_targets.attempts` is the claim epoch AND the retry counter, incremented
by every claim (ordinary, forced, reclaimed). Every terminal transition guards on
`status='running' AND attempts = <the claimed epoch>`, not on `status='running'`
alone: a status can only answer "is this row running?", never "is it still running
under MY claim?". Without the epoch, a worker whose claim was revoked mid-call
passes the old guard and writes its stale verdict over the row of the worker that
now owns the target, whose own write then matches nothing and is dropped. Thread
the claimed epoch through every write path (`finalize_completed`, `mark_skipped`,
`mark_failed`, `record_attempt_error`, `defer_to_pending`) and keep "no epoch
known" expressible for the paths that legitimately have none — passing a wrong
epoch silently bypasses the fence.

`reclaim_stale_targets` runs at the head of each cycle and resets `running` rows
whose `updated_at` is older than `EVAL_CLAIM_LEASE_SECONDS` (120) back to
`pending`. This is not a nicety: capacity is the count of `running` rows, so
before it existed, `EVAL_GLOBAL_CONCURRENCY` rows orphaned by one restart wedged
the ENTIRE service permanently, for every game, with no log and no recovery. It is
BEST-EFFORT — a failure logs a warning and the cycle continues, because DRA-35
established in history-service's ingest reclaim that aborting the cycle turns a
database blip into a hot loop — and `CancelledError` is re-raised so shutdown
still works. There is no separate reaper task and no unconditional start-up sweep;
a start-up sweep would steal every other replica's live claims.

The worker heartbeats the targets it still owns every
`EVAL_CLAIM_HEARTBEAT_SECONDS` (30), which is what lets the lease be short: it
measures "is the worker alive?", not "could this judge call still be running?", so
a slow call under a live worker is never stolen. The lease MUST stay strictly
greater than the heartbeat (validated in `config.py`) or every live claim goes
stale on the cycle before its next refresh. The epoch is the backstop if a
heartbeat is ever missed under load — the outcome is a duplicated *grading*, never
a duplicated *verdict*. A target over `EVAL_MAX_ATTEMPTS` is marked `failed`
instead of reclaimed again, so a target that reliably kills its worker stops
rather than spending judge budget on every pass forever.

The measured effect of continuous refill is a **scheduling** figure only: 27.4 % →
~63 % pipeline efficiency, ~2.1x wall clock, on real Postgres against a stub judge
with scripted latency and one straggler per four calls. No judge key exists in
this environment, so no real-provider speed-up was measured; at uniform latency
the old shape was already ~93 % efficient. Do not quote the number without that
qualification. Full rationale in
`openspec/changes/dra-46-parallel-evaluation/design.md`.

### MCP surface

The service mounts its own MCP server at `/mcp`, wired in `main.py` and
deliberately NOT in the app factory: the test suites build the app directly and
must not start the MCP session manager. `mcp_server.py` declares only the name and
the exclusion list; the mounting itself is `dragncards_common.mcp`.

Tools are generated from this service's FastAPI OpenAPI schema, so a tool IS its
endpoint — with the endpoint's own request and response models as its schema — and
a tool's name is that endpoint's `operation_id`. There is no hand-written tool
layer that could drift from the API.

**Adding a route adds an MCP tool automatically, so give every route an explicit
`operation_id`.** Without one, FastAPI generates a name from the function and path
(`get_evaluation_games__game_id__evaluations__request_id__get`), and that is what
the tool ends up called.

`EXCLUDED_ROUTES` in `mcp_server.py` keeps three things out, each for a specific
reason:

- `stream_evaluation` (`GET /games/{game_id}/evaluations/{request_id}/stream`) —
  server-sent events. A tool call reads its response to completion and this one
  only completes when the run does, so as a tool it would hang the caller until it
  timed out. Poll `get_evaluation` instead, which reports per-target status and the
  live error detail this service records during a run.
- `clear_evaluations` (`POST /evaluations/clear`) — deployment-global. It clears
  the queue for the whole deployment, including requests the caller never created.
  `delete_evaluation` for a single request by id stays available, so an agent can
  still clean up after itself.
- The `health` and `ready` probes, excluded for every service by the shared
  bootstrap: an LLM client gains nothing from them and they crowd the tool list.

Exclusion applies to MCP only. Every one of those endpoints still works over HTTP,
so nothing here reduces what the dashboard or a human with `curl` can do. The
exclusions are regexes matched against generated OpenAPI paths, so
`tests/unit/test_mcp_server.py` asserts tool names against the real app rather
than reading the list — a pattern that quietly matches nothing looks identical to
one that works.

A judge is still required to get a verdict over MCP, exactly as over HTTP:
`create_evaluation` accepts the request either way, but with no `EVAL_JUDGE_MODEL`
configured every target is recorded as `failed` with the configuration error.

The whole loop these tools exist for is
[Driving the System End-to-End](../../AGENTS.md#driving-the-system-end-to-end) in
the root `AGENTS.md`.

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
