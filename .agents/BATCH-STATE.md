# Batch state — `features/bug-batch-20260727`

Resume point for this batch. If a session was cut off by a usage limit, **read this file first**,
then `git log --oneline` on the integration branch. Nothing in this batch exists only in a chat log.

Keep this file current: update it on every merge and whenever a decision is made, and commit it.
Committing locally is what makes the work durable — do not rely on pushing to `origin`.

## Where things are

Integration branch: **`features/bug-batch-20260727`**, pushed to `origin` at **`ccb0fb9`**.
All batch work merges here as **one squash commit per issue**, subject ending ` (DRA-<n>)`.

**All 19 batch issues are merged and closed. No feature branches or worktrees remain** — only
`wt-integration` is left. Two local branches, `features/history-harden` and
`features/history-play-style-browser`, are from 2026-06-29 and are **the owner's, not this batch's**;
do not delete them.

Done: DRA-5, 7, 8, 9, 10, 11, 13, 14, 15, 16, 17, 18, 19 (partial — see below), 20, 21, 22, 23, 24,
25, 27, 29. Still open: **DRA-6** (umbrella, closes when its children do), **DRA-12** (proposal
written, awaiting the owner's decision), **DRA-30** (new — DRA-19's deferred remainder).

Every new worktree needs `git submodule update --init --recursive` before an agent is given it.

**Remote hygiene.** `origin` carries only `main`, `features/bug-batch-20260727`, and the
`renovate/*` branches (open PRs #306, #307, #230 — the bot's, never delete). Do not push feature
branches.

**No pull request is open, and none may be opened without the owner asking in that moment.** PR #305
was closed earlier; it reopens with `gh pr reopen 305` only on an explicit request.

## Two OpenSpec changes are deliberately still active

`openspec/changes/` should contain exactly these two plus `archive/`:

- **`dra-19-agents-orchestration`** — the specification is complete, but sections 5–7 and tasks
  8.4–8.8/8.10 are unchecked because the seat guard, player-to-player messaging and the
  illegal-action findings store were not built. **DRA-30** implements them against this spec. Do not
  archive it until they are done, and do not re-specify.
- **`dra-12-context-management`** — proposal only, zero source files touched. Awaiting the owner's
  choice between (A), (A)+(C), or all three. (A4), the auto-compaction guard, is safe alone.

## Decisions not derivable from the code

1. **DRA-10 supersedes DRA-7's payload trimming.** Owner ruling: filing DRA-10 *is* the statement
   that the post-DRA-7 behaviour is wrong. Accuracy outranks payload size. DRA-7's other half —
   skipping actions that cannot be a wrong decision, e.g. card searches — is orthogonal and is **kept**.
2. **DRA-14: `eval-1` and `eval-2` verdicts are not comparable.** `EVALUATOR_VERSION` is `eval-2`.
   Stored verdicts are left byte-for-byte; `evaluator_version` is part of the write-back idempotency
   key, so a re-grade records a new verdict instead of deduping.
3. **DRA-25: a round verdict is named by a recorded `round_number`, never by resolving `round_span`.**
   The span is a seq pair. Resolving it would mislabel `eval-1` verdicts *successfully* — wrong in a
   way indistinguishable from right. A verdict with no number reads "Round".
4. **DRA-12: smaller-is-better is not the shared principle.** The judge's context and the chat
   agent's differ because one is round-bounded and non-cumulative while the other is cumulative
   against a hard ceiling. Nothing removes history from a turn that fits.
5. **Placeholders are banned in OpenSpec artifacts** and filling them belongs to whoever archives.
6. **`Done` means ready for the owner's testing**, not that a human has clicked it. See `AGENTS.md`.

## Traps already paid for — do not rediscover these

- **`git worktree add` does not populate submodules.** `external/` comes up empty, game-service's
  typed-action registry is then empty, and its unit tests give 384 collection errors (`Literal[()]`).
  Run `git submodule update --init --recursive`; game-service then gives 378 passed. It also silently
  makes `external/dragncards-mc-plugin/json/steps.json` unreadable.
- **`git worktree remove` refuses outright on a worktree containing submodules**, and
  `git submodule deinit --all -f` does not help. Verify the tree is clean and its work is merged,
  then `rm -rf` the directory and `git worktree prune`.
- **A squash-merged branch is not an ancestor**, so `git branch --merged` is the wrong "is it merged"
  test. To check a branch is fully absorbed, diff *its own touched files* against the integration tip
  — and expect insertions in the `integration → branch` direction that are just the branch's older
  copies of lines a later merge changed.
- **`openspec archive` exits 0 even when it aborts** ("already exists"). Check
  `openspec/changes/archive/` rather than the exit code; use `--skip-specs` if the agent pre-synced
  live specs.
- **Archiving a change that creates a brand-new capability generates a `TBD` `## Purpose` stub.**
  DRA-24 produced one in `openspec/specs/service-mcp-surface/spec.md`. Grep all of `openspec/specs/`
  after every archive, not just the change directory.
- **`spec/typed-game-actions` fails `openspec validate --all` pre-existing on `main`,** and is *not*
  the submodule problem. Expect exactly one failure.
- **`pkill -f "<service>"` matches your own shell** and kills it (exit 144). Kill by port via
  `ss -ltnp`, or by explicit PID.
- **`scripts/lint.sh` runs only `black` for Python — never `ruff check`,** so unused imports pass
  lint. `runtime/compaction.py` has two live F401s. Worth its own issue.
- Known flaky, leave alone: `test_api_jobs::test_cancel_job_records_cancellation_event`,
  `test_list_session_jobs_supports_empty_filtered_result`.
- `EVAL_JUDGE_OPENROUTER_API_KEY` is unset in `services/bifrost/.env`, so any judge-latency figure is
  a projection, not a measurement.

## Check baselines on the integration tip (`8295107`, DRA-35 and DRA-34 merged and archived)

- `./scripts/lint.sh` — clean.
- Unit: game-service **384**, agent-orchestrator **490**, history-service **177**,
  eval-service **258**, shared **38**, dashboard **614** (74 files).
  (Against `98192f3`: DRA-35 added 2 to history-service and 2 to shared; DRA-34 added 3 to
  agent-orchestrator and 5 to the dashboard.)
- `pnpm typecheck` in `services/dashboard` — clean.

**`except A, B:` without parentheses is valid here — do not "fix" it.** `job_event_stream.py` uses it
twice. It is PEP 758, new in Python 3.14, and this repo runs 3.14. It reads like a Python 2 relic and
`ast.parse` accepts it; verify before touching it.
- Integration: agent-orchestrator **28**, history-service **8**, eval-service **13**,
  game-service **63**.
- `openspec validate --all` — 16 passed, 1 failed (the pre-existing one above).
- `pnpm typecheck` in `services/dashboard` — clean.
- Placeholder grep over all of `openspec/specs/` — clean.
- Every commit signed: `git log --format="%h %G? %s"` shows no `N`.

**A flaky pair, pre-existing** — reproduced on `eb0a7e6`, so not caused by this batch:
`test_player_seat_sessions.py::test_a_chat_session_still_spawns_a_memoryless_child` and
`test_builtin_tools_subagents.py::test_spawn_subagent_child_failure_emitted_async` fail
intermittently under xdist with random ordering; both pass in isolation.

## Environment notes

The owner's Docker stack was **rebuilt from this branch on 2026-07-29** and is current with it.
Verified live afterwards: all four services healthy, `/personas` 200 (was 404),
`/games/{game_id}/rounds` and `/games/{game_id}/timeline` present, all four `/mcp/` surfaces
returning 406 (mounted), dashboard back up on 3001, and `/api/openapi` merging **99 paths** across
all four services (game 47, orchestrator 32, eval 10, history 10) with 146 schemas.

**Rebuild it with the project name pinned** — see the compose trap below. Postgres and Valkey were
not recreated (volumes preserved, containers stayed up), only the service containers.
`dragncardsai-llama-cpp-smoke-1` remains in a crash loop; pre-existing and untouched.

All verification servers from the first batch are stopped and the throwaway databases `orch_verify`
and `eval_verify` are dropped.

**Compose trap.** `docker-compose.yaml` declares no `name:`, so Compose derives the project name from
the directory. Running `./scripts/docker.sh` from `wt-integration` creates a **second project**
(`wt-integration`) and dies with `Bind for :::5442 failed: port is already allocated`. Always use
`docker compose -p dragncardsai build` / `up -d` from the worktree. Matching the project name is also
what reuses the `dragncardsai_*` volumes. Do not rebuild from the main checkout instead — it sits on
an older branch and would build the wrong code.

## Second batch — complete

All four issues merged, archived and pushed. **No worktrees or feature branches remain.** The two
local branches `features/history-harden` and `features/history-play-style-browser` are from
2026-06-29 and are the owner's — do not delete them.

- **DRA-31** — CORS wildcard replaced by a configurable dashboard-origin allowlist on **three**
  services, not one. game-service and agent-orchestrator were equally exposed (`DELETE /games/{id}`,
  `DELETE /sessions/{id}`, `POST /sessions/{id}/prompts`), so fixing only history-service would have
  left the hole open while looking closed. eval-service was genuinely deliberate and is unchanged.
- **DRA-12** — (A) + (C) only, per the owner. (B) is **DRA-33**. The agent correctly moved (B)'s
  requirement out of the spec delta into `design.md`, because a delta is applied on archive and would
  have written unimplemented behaviour into the durable spec.
- **DRA-26 + DRA-28** — one real bug (the in-place 404, which originates in *agent-orchestrator*'s
  `get_active_session_by_game_id` requiring `status == "active"`), and **two false premises** proven
  false rather than "fixed": branch mode always did create a new game, and open-board never
  overwrote anything (sha256 identical before/after through the UI). The real defect in both was
  that neither action *said* what it did.
- **DRA-6** auto-closed when DRA-12, its last open child, went Done.

Open: **DRA-30** (seat guard — spec already written, change still active), **DRA-32** (proxy/Swagger
auth — needs the owner's auth-model decision), **DRA-33** ((B), design already written).

**Not filed, deliberately — recorded here and in DRA-28's comment so it is not lost.** The
board-at-time click is still slow and the root cause is *not* payload size: `POST /games` fans out to
≥5 sequential external round trips at a measured 65 ms floor. The two named causes are that the
DragnCards token is re-authenticated per room (the obvious in-memory cache would violate the
no-in-memory-state rule, so it belongs in **Valkey**) and that ephemeral rooms are recreated rather
than reused. The owner was offered this as a follow-up and has not yet asked for it.

**A GPG trap that will recur.** `commit.gpgsign=true` with no `~/.gnupg/gpg-agent.conf`, so the
default 600 s passphrase cache expires mid-session and commits fail with `gpg: signing failed:
Timeout`. Two agents hit it; one silently used `-c commit.gpgsign=false`, so **its commits were
unsigned**. That is harmless here only because each issue lands as one squash commit created by the
orchestrating agent, which *is* signed — verify with `git log --format="%h %G? %s"` and check no
commit on the branch shows `N`. Ask the owner to unlock rather than disabling signing.

## Third batch — in flight

Dispatched off the integration tip `9cffc45`, one worktree and branch per issue, agents committing
locally only. Nothing merged yet. **Merge DRA-35 alone the moment it is ready — the owner said not to
wait for the others.**

- **DRA-35** (Urgent) — **MERGED at `7915ec6`, archived at `175d2e1`, closed.** See the root cause
  below; it is worth reading before anyone touches `resp.py` again.
- **DRA-34** — **MERGED at `33d009c`, archived at `8295107`, closed.** It was a *server* defect, not a
  renderer one, and **not question-specific**. `JobEventStreamService.stream` has two sources for the
  same event — it polls `list_events` *and* forwards the live bus — and almost every publish is
  preceded by an `append_event`, so most live events are a second, earlier copy of a row the stream
  also yields from Postgres. The earliness is the point of the bus; what was missing is that the two
  copies were not *identifiable as one event*, because `serialize_live_event` passed through the bus's
  own id (a Valkey stream entry id or an in-memory counter) while the dashboard de-duplicates on
  `JobEventResponse.id`. `LiveJobEvent` now carries `durable_event_id` and the stream prefers it. Two
  things had hidden this: `aggregateEvents` already kept only the last `failure` "so the UI doesn't
  show duplicate error cards" — the same bug patched at the symptom for one type — and streaming
  chunks already solve it properly via `snapshot_event_id`, which is the shape that was generalised.
  It equally affected `failure`, `completion`, `skill_loaded`, `subagent_started/failed`,
  `compaction_failed`, `cancellation` and both question-resolution events.
  Three deliberate exemptions are commented in place: streaming chunks (`snapshot_event_id`),
  `compaction` (its durable home is a separate compaction job, so no twin exists to duplicate), and
  the two `cancellation` publishes in `prompt_run.py`, which were **removed** rather than converted
  because `mark_job_cancelled` appends that row inside the repository, which has no bus to hand an id
  to. The stream still closes on a cancel via its terminal-job-status path, ~200 ms later.
  `missing_model_config` now persists the payload it publishes, since collapsed copies must agree.
  **It touched none of `play-transcript.tsx`, `play-session-events.ts` or `STREAM_EVENT_TYPES`** — so
  the conflict expected with DRA-30 did not materialise, and DRA-30 now rebases onto its orchestrator
  changes instead.
- **DRA-30** — `wt-dra30`, seat guard / messaging / findings store, implementing sections 5–7 of the
  still-active `dra-19-agents-orchestration` spec. Runs with four sub-agents in that one worktree.
  Migration `0012`. Expect `play-transcript.tsx`, `play-session-events.ts` and `STREAM_EVENT_TYPES`
  to conflict with DRA-34 — resolve as unions, not by picking a side.
- **DRA-36** — `wt-dra36`, Valkey-backed DragnCards token cache (the follow-up recorded below).
  **Owns nothing in `resp.py`** — that file is DRA-35's for this batch.
- **DRA-37** (Low, filed 07-29 16:29) — `wt-dra37`, "copious amounts of Valkey calls": an
  agent-orchestrator trace with 6K+ spans. Scoped to **call-site** reduction only; `resp.py` is
  DRA-35's, so transport-level pooling/pipelining is to be written up in `design.md` and handed back
  for sequencing rather than implemented. The agent must first separate too many commands *issued*
  from too many spans *emitted* per command — DRA-23 opens a `valkey.execute` span for every command,
  so the trace may be cardinality, not waste.
- Two dashboard items also in flight: suppressing the redundant `ask_user` tool card, and question
  card visuals.

Open and not dispatched: **DRA-32** (proxy/Swagger auth — needs the owner's auth-model decision),
**DRA-33** (DRA-12's option (B), design already written).

### DRA-35's root cause — four wrong theories were paid for, do not re-run them

The traceback pointed at `await writer.wait_closed()` in `execute()`'s `finally`, and it was lying.
**asyncio stores one exception instance on the protocol and hands that same object to both the reader
and the close waiter** (`StreamReaderProtocol.connection_lost` does `reader.set_exception(exc)` *and*
`self._closed.set_exception(exc)` with the same `exc`). So on a mid-command reset, `_read_resp` raises
it, the `finally` awaits the close waiter which raises **the same object again**, and although
`except Exception: pass` correctly swallows that second raise, the raise has already appended the
`wait_closed` frames to the object's `__traceback__`. The original exception then finished propagating
carrying a traceback that ended at the cleanup line. Proven by object identity, not argued. The fix
sets `skip_wait_closed = True` on the error path — `writer.close()` still runs everywhere, and the
success path is unchanged and still guarded, because a reset *after* a valid reply must not fail the
command.

Dead theories, all four disproven: (1) a different or older checkout — his HEAD was `9cffc45` with
`resp.py` byte-identical; (2) a stale process — he fully restarted; (3) the `finally` guard "not
holding" — it holds, the damage is the traceback mutation; (4) **`6a4972e` (DRA-23, OTel) as the
regression boundary** — refuted by reading the diff: it only wraps `process_batch` in a span,
`reclaim_pending()` was already the first unguarded statement, and the `logger.exception` +
`sleep(0.5)` pair is byte-identical in `6a4972e^`. The amplification predates DRA-23. That suspect was
mine, on the strength of its 07-28 22:48 timestamp matching "yesterday it worked"; a timestamp is not
a mechanism.

**The resets themselves are still not root-caused and are probably environmental.** The owner's Docker
stack ran an hour with zero occurrences over the compose network; the reporter runs outside Docker
against host-published ports. Chasing further needs his host setup. What was fixed is the
amplification, which was real either way: ~1440 log lines per 60s outage became 18, and ~86400 per
hour became 136. A failing reclaim pass no longer discards the whole batch (unclaimed entries stay in
the PEL, which is what `XAUTOCLAIM`'s idle window is for), retries back off 0.5s→30s with one
traceback per outage plus a recovery line, and four Bifrost model-cache warnings lost `exc_info=True`
because that degradation was already correct. Still surfaced unchanged: a failing `XREADGROUP`,
failing commit, failing `XACK`, malformed envelopes. Nothing is acked without a successful commit.

**Deferred, measured, not built: connection pooling in `resp.py`.** The client opens one TCP
connection *per command* — measured at **3 connect+teardown per idle ingest poll, forever**. That
churn is why a mid-command reset is plausible rather than exotic, so it is the real long-term fix, but
it touches shared code four services depend on and DRA-35 was urgent. **DRA-37 is scoped to call sites
precisely so it does not collide with this**, and its `design.md` is to carry the write-up. Sequence
it deliberately, as its own change.

## Known follow-ups worth filing as issues

- **`history-service` sets `allow_origins=["*"]` with `allow_methods=["*"]`** — any page a developer
  visits can `DELETE` straight at 4004, bypassing the dashboard proxy's cross-site check. eval-service
  is correctly stricter. The highest-value one here.
- **No auth on the dashboard proxy or `/swagger`.** No capability is new, but the playground now
  advertises destructive endpoints across four services. Needs a `middleware.ts` — a product decision.
- **`DELETE /sessions/{id}` returned 500** against the running (old) stack. DRA-19 fixed a *different*
  delete defect (orphaned seat sessions), so this may already be gone on the branch — verify.
- No fetch timeout on the Swagger merge: one wedged upstream stalls `/swagger` for undici's 300 s
  default. `swagger-workspace.tsx` also builds the 166 KB merged document twice per page view.
- Add `ruff check` to `scripts/lint.sh`.
- **Connection pooling / pipelining in `dragncards_common.resp`** — one TCP connection per command,
  3 connect+teardown per idle ingest poll. Measurements are in DRA-35's archived change. The single
  highest-value Valkey change left, and deliberately not folded into DRA-35 or DRA-37.
