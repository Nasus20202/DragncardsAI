# Design: parallel evaluation without losing, duplicating, or wedging work

The reporter's third sentence — "Remember about the synchronization" — is the
whole of this document. Making evaluation faster is a small change to a loop.
Making it faster *without* producing two verdicts for one move, a roll-up scored
from half its children, or a service that never recovers from a restart is where
the decisions are. Each section below states the invariant, the mechanism that
enforces it, and the alternatives rejected.

## The invariants

These must hold at all times, under any interleaving, across any number of
replicas, and across a crash at any instruction:

- **I1 — at most one grading per claim.** Two workers must never both run a
  judge call for the same target under the same claim.
- **I2 — at most one verdict per claim.** A worker whose claim has been revoked
  must not write a verdict, and must not overwrite the row of the worker that
  now owns it.
- **I3 — a roll-up never scores a partial set.** A round or game verdict is
  produced only when every child target in its span is terminal.
- **I4 — no claim is held forever.** A worker that dies must give its claim back
  without operator intervention.
- **I5 — no claim state in process memory.** Required by the repo rule, and also
  the only way I1–I4 can hold across replicas.
- **I6 — the concurrency cap is a real bound.** Not per-replica; global.

## Decision 1: keep the claim in Postgres; do not add a Valkey lease

**Chosen:** the claim, the lease, and the epoch are all columns of the
`evaluated_targets` row, mutated by conditional `UPDATE`s.

The brief points at `session_operation_lock` (Valkey `SET NX PX` + Lua
compare-and-delete) as the repo's established work-claim pattern, and it is —
for game-service, which needs a lock over an entity whose state lives in
DragnCards, outside its own database. eval-service is not in that position, and
copying the pattern here would make things worse:

1. **eval-service has no Valkey client, config, or compose wiring at all.** It
   is Postgres-only by design; `AGENTS.md` has a section, *"Concurrency lives in
   the claim, not in the process"*, saying so. Adding a Valkey dependency to get
   a lease is a new failure domain for the service's core loop.

2. **The claim already exists and is already atomic.** `pending → running` is
   one conditional `UPDATE ... WHERE status='pending' RETURNING *`. That single
   statement *is* the mutual exclusion — it is not a lock protecting a claim, it
   is the claim. There is nothing for a lock to add.

3. **A Valkey lease would split one fact across two stores that can disagree.**
   The row says `running`; the lease key has expired. Which is true? Now every
   read path needs both stores and a reconciliation rule, and the failure mode
   (Valkey evicts under memory pressure, or the two are briefly partitioned)
   silently unclaims live work. Keeping `status` and its lease in the same row
   means one `UPDATE ... WHERE` decides both together, atomically, and a crash
   between them is impossible because there is no "between".

4. **It buys nothing the row does not already give.** `updated_at` is already
   written on claim and on every transition. The reaper an expiry would drive is
   a `WHERE updated_at < now() - lease` predicate over data that is already
   there and already maintained.

5. **DRA-10 already ruled on this**, listing "a distributed (Valkey) concurrency
   lease" as an explicit non-goal: *"The durable Postgres claim already bounds
   in-flight work per drainer without adding an infrastructure dependency to a
   service that has none."* Nothing has changed to reverse that.

This satisfies I5. The repo rule is that state must not live *in memory*;
Postgres is the sanctioned home for persistent state, and a claim on a durable
row is persistent state. The rule's preference for Valkey covers ephemeral data
that would otherwise need a table of its own — not an attribute of a row that
already exists.

**Rejected: Valkey `SET NX PX` per target.** Reasons 1–4.
**Rejected: a Postgres advisory lock held for the duration of the evaluation.**
Advisory locks are tied to a session; holding one across a multi-second judge
call ties up a connection per in-flight target and, worse, a lock held by a
crashed backend is released only when Postgres reaps the connection, which is a
TCP-keepalive-timeout question, not a policy we control. The lease is explicit
and tunable; a connection-lifetime lock is neither.

## Decision 2: one `attempts` column is both the claim epoch and the retry counter

**Chosen:** `attempts INTEGER NOT NULL DEFAULT 0`, incremented by every claim.
Terminal writes are conditional on `status='running' AND attempts = :claimed`.

### Why an epoch is required before reclaim can be added at all

Every terminal transition today guards on `status='running'`
(`_transition_running`). That guard answers *"is this row running?"* — but the
question that matters is *"is this row still running **under my claim**?"*, and
a status value cannot answer it. The counterexample is real and already live via
the force path:

| t | Worker A | Reclaim / force | Worker B |
| --- | --- | --- | --- |
| 1 | claims 7, `running`, judge call starts | | |
| 2 | | resets 7 → `pending` | |
| 3 | | | claims 7, `running`, judge call starts |
| 4 | judge returns, `WHERE status='running'` **passes** | | |
| 5 | writes stale verdict, marks `completed` | | |
| 6 | | | own write finds `completed`, matches nothing, **silently dropped** |

The row ends holding **A's abandoned verdict**, marked `completed`, while B's —
the one the user asked for — is discarded. If B was run under a different judge
config (the usual reason to force), the two verdicts hash to different
idempotency keys, so history gets a zombie event the user never requested.

Adding a reclaim path adds a third actor that can reset a row, which widens this
window rather than creating it. So the epoch is a **prerequisite** for reclaim,
not a companion feature. With it, step 4's `WHERE ... AND attempts = 1` fails
against a row now at `attempts = 2`, and A's write is discarded — which is
correct, because A's claim was revoked at step 2.

### Why one column rather than two

A claim epoch and an attempt count are the same monotonic integer: every claim
is a new attempt and a new epoch. Two columns would need to be kept equal for no
benefit. Reading it as a counter gives the poison guard for free — a target
whose `attempts` exceeds `EVAL_MAX_ATTEMPTS` (existing setting, default 3) is
marked `failed` instead of being reclaimed a fourth time.

That guard is not optional. A target that reliably kills its worker — an
oversized prompt, a pathological timeline, an OOM — would otherwise be reclaimed
forever, and each pass **spends judge budget before crashing**. Unbounded
reclaim of a poison target is a money leak and a crashloop generator.
`history-service` reaches the same place by a different route: it acks and drops
an entry it can never decode, on the same principle that an infinitely retried
poison item wedges the queue.

### The epoch has to be checked twice, and one gap remains

Fencing only the row would be too late. The write-back sequence is: re-check the
target, write the verdict **event to history**, then finalize the row. A guard
on `finalize_completed` alone stops a superseded worker from corrupting the
*row*, but only after its history event has already been emitted. So the
pre-write-back re-check compares the epoch as well as the status — a row that
was reset and re-claimed is `running` again, and a status-only test passes it.

That narrows the window; it does not close it, and the design does not pretend
otherwise. The history write is not transactional with the row, so a reclaim
landing between the re-check and the write still lets one stale event through.
Two things bound the damage: history dedupes on
`(game_id, idempotency_key)`, so if the re-evaluation runs under the same judge
config the duplicate collapses to one event; and the row itself is always
correct, because the epoch fence on `finalize_completed` is unconditional.
Closing the gap entirely would mean a distributed transaction across two
services, which is far more machinery than a rare duplicate history event under
a changed config justifies.

**Rejected: a UUID claim token.** Equivalent fencing power, but not orderable,
so it cannot double as the attempt count and needs a second column anyway.
**Rejected: fencing on `updated_at`.** It is not monotonic per claim — the
heartbeat bumps it mid-evaluation, so a worker's own heartbeat would invalidate
its own terminal write.

## Decision 3: a lease with a heartbeat, not a lease sized to the worst judge call

**Chosen:** the worker bumps `updated_at` on the targets it still owns once per
cycle (`EVAL_CLAIM_HEARTBEAT_SECONDS`, default 30). Reclaim resets rows whose
`updated_at` is older than `EVAL_CLAIM_LEASE_SECONDS` (default 120).

The competing option is a fixed lease long enough that no live judge call could
ever exceed it. That forces a choice between two bad settings:

- **Too short** and a genuinely-running slow call is reclaimed and re-graded.
  Not a correctness failure (the epoch discards the loser's write) but it is
  paid-for work thrown away, and it happens exactly when the provider is
  slowest, i.e. when capacity matters most.
- **Too long** and I4 degrades: after a crash the wedged capacity is unavailable
  for the whole lease. Sized against a worst-case judge call plus retries, that
  is many minutes of a dead service.

A heartbeat separates the two questions. The lease then measures **"is the
worker alive?"**, not "could this call still be running?", so an unusually slow
judge call is safe as long as its worker is alive — which is the property that
actually matters. `120 / 30 = 4` missed heartbeats before reclaim tolerates
event-loop stalls and a slow database round trip without being trigger-happy,
and bounds post-crash recovery at ~2 minutes.

**On the heartbeat and I5:** the set of target ids to heartbeat is derived from
the tasks the loop is currently awaiting. That is not claim state — the claim is
the row. If the process dies, the heartbeat stops, which is precisely the signal
the lease is reading. A second replica reads the same rows and reaches the same
conclusions, because it reads Postgres.

**The epoch is the backstop, and it is what makes an aggressive lease safe.** If
a heartbeat is ever missed under load and a live target is reclaimed, the
outcome is a duplicated *grading*, never a duplicated *verdict*: the original
worker's write is fenced by `attempts`. I2 holds unconditionally; I1 holds
except across a missed heartbeat, and degrades to wasted spend rather than
corruption. That asymmetry is deliberate — it is why the lease can be set for
fast recovery instead of for worst-case safety.

## Decision 4: reclaim runs at the head of the cycle and is best-effort

**Chosen:** `reclaim_stale_targets()` is the first step of each worker cycle,
wrapped so that a failure logs a warning and the cycle continues.

Directly modelled on `history-service`'s ingest loop, including the reason it is
best-effort. DRA-35 established there that letting a failed reclaim abort the
cycle produces a **hot loop**: the batch is never read, the loop retries
immediately, and a transient database blip becomes a busy spin. eval-service has
the same shape and would fail the same way. `asyncio.CancelledError` is re-raised
rather than swallowed so shutdown still works.

No separate reaper task, for the same reason history-service has none: a second
task is a second thing to supervise, restart, and reason about, and the cadence
it would need is the cadence the worker already runs at.

**On start-up:** no special sweep. A restarted worker's first cycle runs the same
reclaim, and rows orphaned by the previous process are reclaimed once their
lease expires. A start-up sweep that reset `running` rows *unconditionally*
would be actively wrong with multiple replicas — it would steal the live claims
of every other running replica.

## Decision 5: continuous refill, with the bound still read from the database

**Chosen:** the worker holds its in-flight tasks and waits on
`asyncio.wait(..., return_when=FIRST_COMPLETED)`, re-claiming as soon as any
task finishes.

Measured cost of the current batch barrier (real worker, scripted-latency stub
judge, 24 targets, per-game cap 4): **93.3 %** efficiency when every judge call
takes the same time, **48.5 %** under an LLM-like latency spread, **28.4 %** with
one straggler per four calls. The barrier costs nothing at uniform latency and
about half the throughput at realistic variance — because a freed slot waits for
the slowest member of its batch.

**The task set is not the bound, and must never become it.** `AGENTS.md`
explicitly forbids reintroducing a semaphore or a per-game dictionary. The set
exists because something has to hold an `asyncio.Task` to await it; capacity is
still computed by `claim_pending_targets` from `COUNT(status='running')` in the
claiming transaction. The test that a reviewer should apply: *if this replica's
task set were emptied, would the cap still hold?* Yes — a second replica reads
the same `running` rows and claims the same remaining capacity, having never
seen this replica's tasks.

Completions are **harvested in bulk** per wake: every task that finished is
collected, then one claim covers all the freed slots. This matters because each
claim triggers one `list_all_events` per game, and refilling one slot at a time
would multiply history-service round trips by the number of targets. Bursts of
simultaneous completions — the common case, since a batch of similar prompts
finishes at similar times — coalesce back into one read.

`drain_once` is kept as the one-batch entry point. The existing unit and
integration suites drive it directly, and keeping it means the change is a new
loop *around* unchanged per-target semantics rather than a rewrite of the path
that produces verdicts.

**Rejected: N worker tasks per replica.** Judge calls are I/O-bound, so N
supervisor loops in one event loop add database polling without adding
parallelism. Concurrency within a replica already comes from concurrent tasks
under one loop.

## Decision 6: serialize the claim transaction so the cap is a real bound

**Chosen:** `pg_advisory_xact_lock` at the start of the claim transaction, on
PostgreSQL only.

`FOR UPDATE SKIP LOCKED` locks the *pending candidates*. It does not lock the
`running` rows the capacity `COUNT` reads. Under READ COMMITTED, two replicas
claiming at once each see the pre-claim count and each spend the same capacity,
so the global cap overshoots by up to the replica count — violating I6. This is
not a double-grading bug (claimed sets stay disjoint), it is a **spend-control**
bug: the cap is documented in four places as the guard against stampeding the
provider, and one that doubles when someone scales to two replicas is not a
guard.

A transaction-scoped advisory lock is the cheapest correct fix: it is released
automatically at commit, rollback, *and* backend crash, so unlike the lease it
introduces no new stuck state. Claims serialize against each other; each is a
`COUNT`, a bounded `SELECT` and one `UPDATE`, single-digit milliseconds, against
work items that take seconds. Evaluation itself is untouched and stays fully
concurrent.

SQLite (tests) already serializes writers, so the lock is skipped there, matching
how `FOR UPDATE SKIP LOCKED` is already applied dialect-conditionally.

**Rejected: `SERIALIZABLE` isolation.** Correct, but converts the race into
serialization failures the caller must detect and retry — more moving parts than
one lock, for the same outcome.
**Rejected: `SELECT ... FOR UPDATE` over the running rows.** Locks a set that
grows with in-flight work, for a count.

## Decision 7: exclude saturated games in SQL, not in Python

**Chosen:** the candidate `SELECT` excludes games already at their per-game cap.

Today the query takes the 64 oldest pending rows and *then* drops the ones over
their game's cap in Python. `EVAL_MAX_TARGETS_PER_REQUEST` is 200, so one
whole-game request routinely leaves more than 64 pending rows for one game. Once
that game is saturated every candidate is discarded, the claim returns empty,
and **no other game is ever considered** — a second user's evaluation waits
behind the first game's whole cascade while global capacity sits idle. Filtering
before the window is taken means the 64 rows are spent on games that can accept
work.

**Ordering is preserved exactly.** The `ORDER BY created_at, id` stays, and with
it the property I3 depends on for liveness: a cascade's move targets are planned
and claimed before its roll-ups, so they hold lower ids and are always offered
first. A roll-up therefore cannot occupy the last slot while its own children
wait for one. This change removes whole *games* from the candidate set; it never
reorders targets within a game.

## How the invariants are discharged

| | Mechanism |
| --- | --- |
| **I1** | Conditional `UPDATE ... WHERE status='pending' RETURNING *` — only the transaction that flips the row gets it. `FOR UPDATE SKIP LOCKED` avoids contention on Postgres. Degrades to duplicated *grading* only across a missed heartbeat; never duplicated verdicts. |
| **I2** | `attempts` epoch: every terminal write is `WHERE status='running' AND attempts = :claimed`. A revoked claim's write matches nothing. History's `(game_id, idempotency_key)` unique constraint is the final backstop. |
| **I3** | `count_nonterminal_children` over the roll-up's span, re-read from Postgres on **every** attempt; a roll-up with non-terminal children defers to `pending` without grading. Reclaim strengthens this: before it, one child stuck `running` blocked its roll-up forever. |
| **I4** | Lease + heartbeat + `reclaim_stale_targets` at the head of each cycle; `attempts > EVAL_MAX_ATTEMPTS` → `failed` so a poison target stops rather than looping. |
| **I5** | Every one of the above is a column of `evaluated_targets` read and written through conditional SQL. No semaphore, no queue, no per-game dict, no claim set. |
| **I6** | `pg_advisory_xact_lock` around the capacity count and claim. |

## What this design does not establish

The wall-clock improvement against a real provider is **unmeasured and
unmeasurable in this environment**: `EVAL_JUDGE_OPENROUTER_API_KEY` is unset,
`judge_configured` is `false`, every provider reads `available=false`. Every
figure here comes from the real worker path driven by a stub judge with scripted
latency, which measures *scheduling* faithfully and says nothing about provider
behaviour. The projected gain is the ratio of pipeline efficiencies under an
assumed latency distribution — ~1.9× on the realistic-spread profile, falling to
~1× as real judge latency becomes uniform. Whether production latency has that
variance is untested.

The reclaim path is exercised by advancing `updated_at` on rows and by killing
tasks mid-evaluation, not by killing a container. A real SIGKILL of a real
replica against a real Postgres is not reproducible here, since running Docker
is prohibited for this change.
