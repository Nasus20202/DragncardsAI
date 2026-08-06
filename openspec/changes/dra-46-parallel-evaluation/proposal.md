# Keep every evaluation slot busy, and give a dead worker's claim back

## Why

The reporter asked for parallel evaluation:

> Move evaluation should be done in parallel, to reduce the wait time. Multiple
> worker can pick them up asynchronously. Remember about the synchronization.

Evaluation is *already* concurrent. DRA-10 deleted the worker's in-process
semaphores and moved the bound into the durable claim: `claim_pending_targets`
counts the rows already `running` and takes only the remaining global
(`EVAL_GLOBAL_CONCURRENCY`, 8) and per-game (`EVAL_PER_GAME_CONCURRENCY`, 4)
capacity, so the cap survives a restart and holds across replicas. Round and
game roll-ups already defer themselves back to `pending` while their children
are still in flight. Targets are already deduplicated by a UNIQUE
`(game_id, target_seq, scope, player)` constraint.

So this change is not "add parallelism". It is the two defects that stop the
parallelism already there from actually reducing wall-clock time — one a
throughput bug, one an availability bug. Both were found by measurement, and
both are squarely the "remember about the synchronization" the reporter flagged.

### 1. The drain waits for the whole batch before refilling a single slot

`EvaluationWorker.drain_once` claims a batch, starts a task per target, then
`await asyncio.gather(*tasks)` — and only *then* returns, so `run_forever` can
claim again. The claim is capacity-bounded, so the batch is at most the cap.
The consequence is a **barrier**: no freed slot is refilled until the *slowest*
target in the batch finishes.

Measured on the real worker path with a stub judge whose latency is controlled
(24 move targets, one game, per-game cap 4; `ideal` = total judge work ÷ 4,
the wall clock a perfectly-refilled pipeline would achieve):

| Judge latency profile | wall clock | ideal | efficiency |
| --- | --- | --- | --- |
| Uniform 100 ms (control) | 0.643 s | 0.600 s | **93.3 %** |
| LLM-like spread (60–450 ms) | 2.212 s | 1.073 s | **48.5 %** |
| One 400 ms straggler per 4, rest 20 ms | 2.431 s | 0.690 s | **28.4 %** |

The occupancy trace shows the mechanism exactly — judge calls start in lockstep
bursts of 4 at t = 0.029, 0.434, 0.839, 1.244 s, one burst per straggler, with
three of the four slots idle for ~0.38 s of every 0.40 s cycle.

The control row is the honest bound on this: **when every judge call takes the
same time, the barrier costs nothing.** The loss is entirely a function of
latency variance, and LLM completion latency is famously variable — it scales
with output tokens, and a judge that emits a long rationale for a complicated
move takes several times as long as one that rubber-stamps a simple one. Under
the realistic-spread profile the barrier is costing about half the throughput
the configured concurrency already pays for.

### 2. A worker that dies takes the whole service down with it, permanently

There is no reclaim path anywhere in eval-service. A target is claimed by
`UPDATE ... SET status='running'` and nothing ever moves it out of `running`
except the worker that claimed it. If that worker is killed, redeployed, or
OOMs mid-evaluation, the row stays `running` **forever**.

That is not merely a stuck target. `claim_pending_targets` computes
`capacity = global_limit - count(status='running')`, so orphaned rows
permanently consume global capacity. Demonstrated against the real repository:

```
claimed-then-orphaned rows: 8      (= EVAL_GLOBAL_CONCURRENCY)
  fresh-worker claim cycle 0: 0 targets
  fresh-worker claim cycle 1: 0 targets
  ... (every subsequent cycle: 0)
pending targets never claimable again: 12
```

Eight orphaned rows — one ordinary restart during a whole-game cascade — and
the eval-service **never evaluates anything again**, for any game, until someone
edits the database by hand. There is no alert, no log, no recovery. The service
simply goes quiet. This is the more serious of the two defects, and increasing
parallelism without fixing it makes it strictly more likely to fire, because
more rows are `running` at any instant.

### 3. Reclaim cannot be bolted on safely without a claim epoch

The obvious fix — reset stale `running` rows to `pending` — is unsafe against
the current schema, and so is the force-reclaim path that already exists.
Terminal writes guard on `status='running'` (`_transition_running`). That guard
distinguishes *running from not-running*; it cannot distinguish **this** claim
from a **later** one. Sequence:

1. Worker A claims target 7 (`running`), starts a slow judge call.
2. A reclaim (or a user's force re-evaluation) resets 7 to `pending`.
3. Worker B claims 7 (`running` again) and starts grading.
4. Worker A's call returns and writes its verdict. The row *is* `running`, so
   the guard passes — and A's stale verdict lands, then B's overwrites it.

Two judge calls, two verdict write-backs, for one target. The row-level guard
cannot see that the claim it belongs to is over. A reclaim mechanism that adds
a *third* way for a row to be reset makes this window wider, so the epoch is a
prerequisite for reclaim rather than a nice-to-have alongside it.

### 4. The cap does not actually hold across replicas

`claim_pending_targets` computes capacity from an **unlocked**
`COUNT(*) WHERE status='running'`. `FOR UPDATE SKIP LOCKED` locks the *pending
candidates*; it does not lock the running rows being counted. Under Postgres'
default READ COMMITTED, two replicas claiming simultaneously each see the
pre-claim count, each compute the full remaining capacity, and each claim up to
it — so the global cap can be overshot by a factor of the replica count.

This never causes double-grading: the claimed row sets are disjoint, guaranteed
by the conditional `status='pending'` UPDATE. It only breaks the *bound* — which
is the whole point of the caps, documented in `README.md`, `.env.example`,
`AGENTS.md` and `docker-compose.yaml` as the guard against stampeding the
provider. A cap that silently doubles with a second replica is not a spend
control.

### 5. One busy game starves every other game

`drain_once` asks for `limit=64` candidates, and the candidate SELECT takes the
64 oldest pending rows **before** per-game capacity is applied in Python.
`EVAL_MAX_TARGETS_PER_REQUEST` is 200, so a single whole-game request routinely
leaves more than 64 pending rows for one game. Once that game sits at its
per-game cap, all 64 candidates are rejected by the capacity filter, the claim
returns `[]`, and **no other game's targets are ever looked at** until the busy
game's backlog drops below 64. A second user's evaluation waits behind the first
game's entire cascade despite global capacity being free.

## What Changes

### 1. Continuous refill replaces the batch barrier

`run_forever` becomes a supervisor loop that holds the in-flight tasks and waits
on `asyncio.wait(..., return_when=FIRST_COMPLETED)` instead of draining a batch
to completion. As soon as **any** evaluation finishes, the loop re-claims and
starts work in the freed slot. Every completed task is harvested per wake, so a
burst of simultaneous completions coalesces into one claim and one history read
rather than one per target.

The concurrency bound does not move into the loop. It stays exactly where DRA-10
put it — `claim_pending_targets` counting `running` rows in the claiming
transaction. The task set the loop holds is lifecycle bookkeeping (something has
to hold an `asyncio.Task` to await it), never the bound; a second replica is
still bounded correctly because the bound is read from the database, not from
either replica's task set.

`drain_once` is kept as the single-batch entry point the existing tests and the
integration suite drive, so the change is a new loop shape around unchanged
per-target semantics rather than a rewrite of the evaluation path.

### 2. A claim epoch on the target row, reusing an attempt counter

`evaluated_targets` gains one column, `attempts INTEGER NOT NULL DEFAULT 0`,
incremented by every claim (normal, forced, or reclaimed). It is the claim
epoch and the retry counter at once:

- **As an epoch**, it closes the stale-write window above. `claim_pending_targets`
  returns the attempt number it wrote, and every terminal transition for that
  target is conditional on `status='running' AND attempts = <the claimed one>`.
  Worker A's late write in step 4 above now fails its `WHERE` clause and is
  discarded, because the row has moved to a later epoch. This hardens the
  pre-existing force-reclaim path as a side effect.
- **As a counter**, it bounds poison retries. A target reclaimed more than
  `EVAL_MAX_ATTEMPTS` (existing setting, default 3) times is marked `failed`
  with a clear reason rather than being handed to a fourth worker. Without this,
  a target that reliably kills its worker — an oversized prompt, a pathological
  timeline — would be reclaimed forever, and the reclaim loop would be a
  crashloop generator that also spends judge budget on every pass.

One column serves both because a claim epoch and an attempt count are the same
monotonic number; adding two would mean keeping them consistent for no gain.

### 3. Stale claims are reclaimed, with a heartbeat so live work is never stolen

`Repository.reclaim_stale_targets()` resets `running` rows whose `updated_at` is
older than a lease window back to `pending` (or to `failed` once `attempts`
exceeds `EVAL_MAX_ATTEMPTS`). The worker calls it at the head of each cycle,
exactly as `history-service`'s ingest calls `reclaim_pending()` at the head of
each poll — and, like that one, **best-effort**: a reclaim failure logs a warning
and the cycle continues, because DRA-35 established in history-service that
letting a failed reclaim abort the cycle produces a hot loop.

A lease needs a liveness signal, or a genuinely-running long judge call gets
stolen and double-graded. The worker therefore **heartbeats** its in-flight
targets, bumping `updated_at` on the rows it still owns each cycle. The lease
window (`EVAL_CLAIM_LEASE_SECONDS`, default 120 s) is then a multiple of the
heartbeat interval rather than a guess at the longest possible judge call, so a
judge call slower than the lease is still safe as long as its worker is alive —
which is the property that actually matters. The epoch guard is the backstop if
a heartbeat is ever missed under load: a wrongly-reclaimed target is re-graded,
but it cannot produce two verdicts.

### 4. The lease lives in Postgres, not Valkey — deliberately

The repo rule is that services keep no state in memory; Postgres for persistent
state, Valkey for ephemeral. This claim lease is in Postgres. `design.md` argues
it in full; the short form is that eval-service has **no Valkey client at all**
today, the claim is already an atomic property of the target row, and moving the
lease to Valkey would split one claim across two stores that can disagree — the
row saying `running` while the lease key has expired — turning an invariant that
a single `UPDATE ... WHERE` enforces into a reconciliation problem. DRA-10
recorded "a distributed (Valkey) concurrency lease" as an explicit non-goal for
the same reason; this change does not reverse that.

### 5. The claim transaction is serialized, so the cap is a real cap

On PostgreSQL the claim takes a transaction-scoped advisory lock
(`pg_advisory_xact_lock`) before counting `running` rows. Two replicas can no
longer both read the pre-claim count and both spend the same capacity; the
second waits, re-counts, and sees the first's committed claim. The lock is
released automatically when the transaction ends, including on crash, so it adds
no new stuck-state of its own. SQLite (tests) already serializes writers and
keeps the existing behaviour.

The cost is that claims are serialized against each other. A claim is a `COUNT`,
a bounded `SELECT` and one `UPDATE` — single-digit milliseconds — while the work
it hands out is a multi-second judge call, so this is not a throughput
constraint at any plausible cap. It is on the claim path only; evaluation itself
stays fully concurrent.

### 6. A saturated game no longer hides other games' work

Games already at their per-game cap are excluded in **SQL**, before the
candidate window is taken, rather than being fetched and then filtered out in
Python. The 64-row window is then spent on games that can actually accept work,
so a second game's targets are claimed while the first game's cascade runs.

### 7. Concurrency defaults are unchanged

`EVAL_GLOBAL_CONCURRENCY` stays 8 and `EVAL_PER_GAME_CONCURRENCY` stays 4. This
change makes the *existing* budget effective rather than raising it — the
measurements show ~2× more throughput at the realistic profile from refill
alone, at identical peak provider load. Raising the caps on top of that would
change peak spend and rate-limit exposure, and should be a separate, deliberate
decision made against real provider latency, which is not measurable here.

## Result

Re-measured after the change, same workload, **against real PostgreSQL** (a
throwaway database per run) so the claim path pays its true round-trip cost.
24 move targets, per-game cap 4, one 400 ms straggler per four 20 ms calls;
three runs each:

| Drain shape | wall clock | efficiency |
| --- | --- | --- |
| Batch barrier (before) | 2.517 / 2.499 / 2.553 s | **27.4 %** |
| Continuous refill (after) | 1.251 / 1.238 / 0.963 s | **~63 %** |

**≈2.1× less wall-clock time on the same concurrency budget**, with peak
in-flight judge calls still capped at 4 and every target completed exactly once
(`attempts = 1` on every row, 24 judge calls, 24 history write-backs).

The efficiency ceiling is lower than the same measurement on in-memory SQLite
(~78 %) because each refill claim is now a real network round trip to Postgres;
that cost is the price of the bound being durable, and it is already counted in
the figure above.

## What was measured, and what was not

Everything above was measured against the real `EvaluationWorker`,
`Evaluator` and `Repository` with a stub judge whose latency is scripted. That
is a faithful measurement of the **scheduling** behaviour: the barrier, the
occupancy trace, and the capacity deadlock are all properties of this code, not
of a provider.

**No end-to-end speed-up against a real judge was measured, and none is
claimed.** `EVAL_JUDGE_OPENROUTER_API_KEY` is unset in this environment, the
service reports `judge_configured: false`, and every provider reads
`available=false`, so no judge call is possible. The 2.1× above is a measurement
of **scheduling** against a stub judge whose latency is scripted — it is real,
reproducible, and paid on real Postgres, but it is not a provider measurement.

How much of it survives against a real provider depends entirely on that
provider's latency variance, which is untested here. The control row is the
honest bound: at uniform latency the old shape was already ~93 % efficient, so
the gain would be ~1×. The straggler profile above is the pessimistic end. A
plausible real distribution sits between them, so the expected real gain is
somewhere in 1×–2×, and the only way to establish where is to run it with a
judge key configured.

One further caveat on the unit-test measurements quoted earlier: the sqlite
fixture shares a single connection (`StaticPool`), so concurrent transactions on
it interleave. Continuous refill exposes that — the same workload that is clean
on Postgres produced duplicate claims against the fixture. The concurrency tests
for this change therefore live in the integration suite, against real Postgres,
where each session holds its own connection. The sqlite figures are retained
only as the mechanism illustration; every correctness claim rests on Postgres.

## Non-goals

- **Raising the concurrency caps.** Deliberately unchanged; see above.
- **A Valkey lease or a distributed lock.** See `design.md`.
- **Multiple worker tasks inside one replica.** Judge calls are I/O-bound, so N
  supervisor loops in one event loop would add database polling without adding
  parallelism. Concurrency within a replica comes from concurrent tasks under
  one loop; concurrency across replicas already works via the durable claim.
- **Changing the roll-up dependency rule.** Round and game roll-ups keep
  deferring to `pending` while children are non-terminal, which is what keeps a
  roll-up from scoring a partial set. Continuous refill does not weaken it,
  because the check is re-run from Postgres on every attempt.
- **Changing prompts, the rubric, the verdict schema, or `EVALUATOR_VERSION`.**
  No verdict's meaning changes, so verdicts stay comparable across this change.

## Impact

- Affected specs: `agent-move-evaluation` (continuous refill; claim epoch;
  stale-claim reclaim and its lease; bounded reclaim attempts; the cap holding
  under concurrent claims; per-game fairness across games).
- Affected code: `services/eval-service/src/eval_service/runtime/worker.py`,
  `runtime/evaluator.py`, `storage/repository.py`, `storage/models.py`,
  `schema_migrations/sql/0003_target_attempts.{postgresql,sqlite}.sql` (new),
  `config.py`.
- Configuration changes: `EVAL_CLAIM_LEASE_SECONDS` (new, default 120),
  `EVAL_CLAIM_HEARTBEAT_SECONDS` (new, default 30). No default concurrency
  changes.
- Schema: one additive column with a default; no backfill, no rewrite. Rows
  written before this change start at `attempts = 0`.
