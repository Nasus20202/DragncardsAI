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

## Check baselines on the integration tip (`ccb0fb9`)

- `./scripts/lint.sh` — clean.
- Unit: game-service **378**, agent-orchestrator **470**, history-service **159**,
  eval-service **252**, shared **36**, dashboard **598** (73 files). Python total 1295.
- Integration: agent-orchestrator **28**, history-service **8**, eval-service **13**.
- `openspec validate --all` — 17 passed, 1 failed (the pre-existing one above).
- `pnpm typecheck` in `services/dashboard` — clean.
- Placeholder grep over all of `openspec/specs/` — clean.

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

## Second batch, in flight as of 2026-07-29

Owner decisions that scope it: **DRA-12 gets (A) + (C), not (B)** — (B) changes *when* history is
summarised and sign-off was withheld; A4 (the guard) ships first. **DRA-31 is fixed now, DRA-32 is
filed** for later because it needs an auth model decision.

| Branch | Issue | Scope |
| --- | --- | --- |
| `stanislaw/dra-26-history-restore-and-board-view` | DRA-26 + DRA-28 | Together on purpose: DRA-26's third bullet ("open board at this event" must not overwrite the live game) *is* DRA-28's subject. Two agents on one surface would collide. |
| `stanislaw/dra-12-bounded-compaction` | DRA-12 | (A) checkpointed + capped + fitted compaction input, A4 guard first; (C) helper text. (B) explicitly untouched. |
| `stanislaw/dra-31-history-cors` | DRA-31 | CORS only, aligned to eval-service, plus a four-service audit. No auth. |

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
