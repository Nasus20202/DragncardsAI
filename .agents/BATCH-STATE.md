# Batch state — `features/bug-batch-20260727`

Resume point for this batch. If a session was cut off by a usage limit, **read this file first**,
then `git log --oneline` on the integration branch and on each feature branch listed below. Nothing
in this batch exists only in a chat log.

Keep this file current: update it on every merge and whenever a decision is made, and commit it.
Committing locally is what makes the work durable — do not rely on pushing to `origin`.

## Where things are

Integration branch: **`features/bug-batch-20260727`**. It is a strict superset of
`features/stachu-changes` (77 archived OpenSpec changes vs 55, no gaps) and 0 commits behind
`origin/main`. All batch work merges here as **one squash commit per issue**, subject ending
` (DRA-<n>)`.

Worktrees: `/home/kanareklife/Projects/.dragncards-wt/wt-dra<n>`. These are on `/home` (btrfs,
dynamic inodes) and **not** in the tmpfs scratchpad, which had ~828k free inodes against the ~1.25M
five dashboard installs need. The pnpm store is on `/home` too, so installs hardlink rather than
copy.

| Branch | Issue | State |
| --- | --- | --- |
| `stanislaw/dra-14-eval-round-boundaries` | DRA-14 | merged as `e7dac43` |
| `stanislaw/dra-18-eval-errors-surfaced` | DRA-18 | merged as `0cae61e` |
| `stanislaw/dra-15-skill-into-message` | DRA-15 | merged as `97b7761` |
| `stanislaw/dra-10-round-scoped-evaluation` | DRA-10 | in progress |
| `stanislaw/dra-13-export-import-history` | DRA-13 | in progress |
| `stanislaw/dra-16-agent-personas` | DRA-16 | in progress |
| `stanislaw/dra-17-history-perf-scroll` | DRA-17 | in progress |

Merged worktrees are removed as soon as their branch lands; the branch is kept.

**Remote hygiene.** Feature branches live only locally — the batch's seven `stanislaw/dra-*` branches
were briefly pushed for durability, then deleted from `origin` at the owner's instruction once
durability moved to frequent local commits. Do not push feature branches. `origin` should carry only
`main`, `features/bug-batch-20260727`, and the `renovate/*` branches (which have open PRs #306, #307,
#230 and are the bot's — never delete those).

**Merge procedure that works here:** rebase the feature branch onto the integration tip *first*
(otherwise the squash reverts newer integration-branch commits — see the `TBD` trap below), grep the
change directory for placeholders, check whether it edited `openspec/specs/` directly, then
`git merge --squash` and commit with a single-line subject ending ` (DRA-<n>)`.

**No pull request is open, and none may be opened without the owner asking in that moment.** PR #305
was closed earlier; it reopens with `gh pr reopen 305` only on an explicit request.

## Decisions not derivable from the code

1. **DRA-10 supersedes DRA-7's payload trimming.** Owner ruling: filing DRA-10 *is* the statement
   that the current post-DRA-7 behaviour is wrong. Accuracy outranks payload size, the context window
   is not capped to protect DRA-7's byte reduction, and no flag preserves the old behaviour. DRA-7's
   other half — skipping actions that cannot be a wrong decision, e.g. card searches — is orthogonal
   to accuracy and is **kept**.
2. **DRA-14: `eval-1` and `eval-2` verdicts are not comparable.** `EVALUATOR_VERSION` is now
   `eval-2`. Stored verdicts are left byte-for-byte; `evaluator_version` distinguishes them and is
   part of the write-back idempotency key, so a re-grade records a new verdict instead of deduping.
3. **Placeholders are banned in OpenSpec artifacts** and filling them belongs to whoever archives.
   See the rule in `AGENTS.md`.

## Traps already paid for — do not rediscover these

- **`git worktree add` does not populate submodules.** `external/dragncards` and
  `external/dragncards-mc-plugin` come up empty, game-service's typed-action registry is then empty,
  and its unit tests give 384 collection errors (`Literal[()]`). Run
  `git submodule update --init --recursive` in every new worktree; game-service then gives 378
  passed. This also silently makes `external/dragncards-mc-plugin/json/steps.json` unreadable, so any
  agent told to consult it for step ids needs its work checked rather than trusted.
- **Filling a `## Purpose` on the integration branch while feature branches sit on an older tip means
  a naive squash-merge reverts the fill and reintroduces `TBD`.** Rebase each feature branch onto the
  integration tip before merging, then re-grep for placeholders.
- **`spec/typed-game-actions` fails `openspec validate --all` pre-existing on `main`,** and is *not*
  the submodule problem — it reproduces with submodules fully populated. Expect exactly one failure.
- Known flaky, leave alone: `test_api_jobs::test_cancel_job_records_cancellation_event`,
  `test_list_session_jobs_supports_empty_filtered_result`.
- `EVAL_JUDGE_OPENROUTER_API_KEY` is unset in `services/bifrost/.env`, so DRA-7's judge-latency
  figure is a projection, not a measurement.

## Check baselines on the current integration tip

- `./scripts/lint.sh` — clean.
- eval-service unit: **210 passed** (178 at the start of the batch).
- dashboard unit: **349 passed** (340 at the start).
- agent-orchestrator unit: **322 passed** (309 at the start).
- game-service 378, history-service 100, shared 16.
- `openspec validate --all` — 16 passed, 1 failed (the pre-existing one above).

## Owed before anything is Done

Merged is not Done. Every issue additionally needs its OpenSpec change archived, `openspec/specs/`
synced, and end-to-end verification by driving the running app through Playwright — not unit tests
alone. Both are deferred to one pass at the end of the batch, because concurrent agents cannot each
run the Docker stack without colliding on ports. DRA-14 and DRA-18 are merged and unit-verified but
deliberately still `In Progress`.

## Not started, by owner instruction

No new agents beyond those in flight until the owner says so. Remaining Todo: DRA-5, DRA-6
(umbrella, closes when its children do), DRA-12 (blocked by its own terms — it defines a written
proposal as the next step), DRA-19, DRA-20, DRA-21, DRA-22, DRA-23, DRA-24, DRA-25.
