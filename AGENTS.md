# DragncardsAI Agent Guide

Read this file before making changes in this repository.

## Scope

These instructions apply to the whole repository unless a deeper `AGENTS.md` overrides them.

This file is the single source of truth for agent instructions, and is read by every
assistant setup used on this project (Claude Code, OpenCode, and any other). Tool-specific
entry files such as `CLAUDE.md` are thin pointers to this file and must stay that way — an
instruction written only in a tool-specific file silently does not apply to everyone else.
Write rules in terms of *what* to do, naming a specific tool or command only as an example.

## Project Overview

- This repository contains an LLM-powered Marvel Champions bot for DragnCards.
- Top-level areas include `services/`, `scripts/`, `external/`, `openspec/`, and `.github/`.
- Primary local workflows are documented in `README.md`.

## Useful Reading

- Start with [`README.md`](README.md) for local setup, test commands, and service URLs.
- Read **[Driving the System End-to-End](#driving-the-system-end-to-end)** below before
  verifying a change by hand. It is the full loop — create a game, start a player agent,
  read its actions, read the live board, request an evaluation, read the verdict — over the
  MCP surface every service exposes, plus the prerequisites that otherwise cost an
  afternoon.
- Read [`services/game-service/README.md`](services/game-service/README.md) when working on DragnCards session control, MCP tools, or game actions.
- Read [`services/agent-orchestrator/README.md`](services/agent-orchestrator/README.md) when working on agent sessions, skills, providers, or background jobs.
- Read [`services/history-service/README.md`](services/history-service/README.md) when working on the recorded event store, snapshots, or restore.
- Read [`services/eval-service/README.md`](services/eval-service/README.md) when working on move/round/game evaluation or the judge.
- Read files nearest to the change before introducing new patterns.

## Service-Level Guides

Service-specific AGENTS.md files override these instructions:

- [`services/dashboard/AGENTS.md`](services/dashboard/AGENTS.md) - Frontend development with Hero UI components
- [`services/game-service/AGENTS.md`](services/game-service/AGENTS.md) - Game service patterns, DragnLang actions, Phoenix Channels
- [`services/agent-orchestrator/AGENTS.md`](services/agent-orchestrator/AGENTS.md) - Session lifecycle, jobs, provider configuration
- [`services/history-service/AGENTS.md`](services/history-service/AGENTS.md) - Event envelope, ordering and idempotency, snapshots and restore
- [`services/eval-service/AGENTS.md`](services/eval-service/AGENTS.md) - Judge identity, prompt projection, round boundaries, verdict write-back

## Working Rules

- Prefer the smallest correct change that fits the existing code style.
- Check nearby code before introducing new abstractions, helpers, or patterns.
- Do not revert or overwrite user changes that are unrelated to your task.
- Keep secrets out of commits and examples.

## Working Preferences

- Do substantive work in an isolated git worktree rather than directly on the checked-out branch.
- Remove a worktree as soon as its work is merged or abandoned, in the same session that finishes it — do not leave worktrees behind for a later cleanup. Each dashboard worktree costs roughly 250k inodes once its `node_modules` is installed, and a scratch filesystem that runs out of inodes stops *every* write, including the writes needed to clean it up. Delete `node_modules` when a worktree's checks are done, remove the worktree when its branch merges, and `git worktree prune` after. Removing a worktree does not delete its branch, so it is always the reversible half of the cleanup — but it *is* destructive to anything uncommitted inside it. Before removing one: confirm the agent that owned it has finished **and** that no instruction is still outstanding to it (a delegated agent can be resumed and start editing again after it has already reported "complete"), then check `git status` in that worktree and commit anything left. A worktree removed while its agent was mid-edit loses exactly the work nobody has a copy of.
- Delegated agents work only in their own worktree and must never edit or commit in the integration worktree — two writers in one tree interleave commits and can leave it dirty mid-check. If an agent needs work carried into the integration branch after its own worktree is gone, it reports what is missing and the orchestrating agent applies it.
- **Delete a feature branch once its work is merged into the integration branch.** A merged branch is leftover clutter, not a safety net — the work lives in the integration branch's history. Do this as part of the same cleanup that removes the worktree, so branches do not accumulate across sessions. Two cautions: squash-merging means a merged branch is *not* an ancestor of the integration branch, so `git branch --merged` will not list it and ancestry is the wrong test — match the branch to the OpenSpec change that archived its work instead. And record the branch tips (`git branch --format='%(refname:short) %(objectname)'`) somewhere outside the repo before a bulk delete, so a mistake stays recoverable. Never delete `main`, the current integration branch, a branch that is checked out in some worktree, or a `features/*` branch the owner created; and never delete a remote branch that backs an open pull request.
- Delegate as much as reasonably possible to delegated agents; fan out independent pieces in parallel.
- Run implementation agents on the most capable model available, never a fast or cheap tier (in Claude Code, pass `model: opus`).
- Multi-feature sessions branch off a single integration branch: each feature/agent gets its own worktree branch off the integration branch, works independently, then merges back as **one squash commit per feature**.
- **Never open a pull request unless the owner explicitly asks for it in that moment.** Merging features into the integration branch and pushing it is the end of the agent's job; the PR is the owner's call, every time. A rule stating that PRs are opened from the integration branch describes *which branch* a PR comes from — it is not standing permission to open one, and neither is an unanswered earlier question about it. Silence is not consent.
- **One** integration branch per session, chosen once and kept. Work that arrives later in the session joins the existing integration branch — a new source of work (issues instead of chat reports, a new batch of bugs) is not a new session and does not justify a second integration branch. Two live integration branches mean two PRs that stack on each other for no reason.
- Skip the worktree/delegation overhead for trivial one-off edits.
- **Durability comes from committing often on the local branch, not from pushing.** A session can end at any moment — on a usage limit, a crash, a closed terminal — and uncommitted work is the only work that dies. Commit each coherent piece as it lands (a passing test, a migration, a section of a proposal), with `wip:` on the subject while the state is partial; squash-on-merge means intermediate commits cost nothing. Do not push to `origin` merely to feel safe: the local commit is what preserves the work, and pushing is a separate, deliberate act. Keep a resume file (`.agents/BATCH-STATE.md`) current in the same commits, so the next session recovers the plan and the decisions from the branch itself rather than from a chat log that no longer exists.
- Commits use a single-line message and must NOT include any AI attribution (no `Co-Authored-By` trailer naming an assistant).
- Every change goes through the OpenSpec workflow (a change in `openspec/changes/`), even small fixes.
- After implementing a change, ensure the main specs in `openspec/specs/` are brought up to date (sync/archive) so specs reflect reality when the work is done.
- **`TBD` is never acceptable in an OpenSpec artifact.** Neither is any other placeholder standing in for content that was meant to be written: `TODO`, `???`, `to be decided`, an empty section under a heading, or a `## Purpose` left holding the generator's own "update after archive" note. Archiving a change is what creates or updates a spec, so archiving is exactly when every placeholder it produced must be replaced with real prose — a spec is the durable record of what the system does, and a placeholder there is a lie that outlives the change that introduced it. Filling them in is the responsibility of whoever archives, not a follow-up for someone else. Before archiving, grep the change and the specs it touches for placeholder text and resolve each one; if something genuinely cannot be decided yet, write what is actually known and what the open question is, in prose, rather than leaving a marker.
- After each bigger implementation, run the code-review, security-review, and simplification passes (the `/code-review`, `/security-review`, and `/simplify` commands where the setup provides them) and address their findings before considering the work done.
- Use `pnpm` / `pnpx` for all Node tooling — never `npm`, `npx`, or `yarn`.
- Always verify new features end-to-end by driving the running app through the Playwright MCP server and clicking through the feature — don't rely on unit/integration tests alone.
- Track work in Linear, per **Task Management (Linear)** below.

## Task Management (Linear)

Linear holds *what* work exists and what state it is in. `openspec/` holds *how* a change is
specified. A chat log holds nothing durable — anything recorded only there is lost.

Workspace: team **DragncardsAI**, issue prefix `DRA`. Statuses `Backlog → Todo → In Progress →
Done`, plus `Canceled` and `Duplicate`. Labels `Bug`, `Feature`, `Improvement`.

The step-by-step procedure and the comment templates live in the `linear-workflow` skill
([`.agents/skills/linear-workflow/SKILL.md`](.agents/skills/linear-workflow/SKILL.md)); the rules
below are the policy it implements. Reaching Linear needs a Linear MCP server configured in the
assistant setup.

Assistant-facing skills like that one live under `.agents/skills/` and are symlinked into
`.claude/skills/` and `.opencode/skills/`. They must NOT go in the repo-root `skills/` directory:
that is a *runtime* skill root, enumerated by the agent-orchestrator and eval-service and copied
into their images, so anything placed there is offered to the game-playing agent and the judge as
a Marvel Champions skill. `skills/` is for game and domain knowledge only.

### Work order when pulling issues from Linear

Sort the fetched issues by, in this order:

1. **Priority** — Urgent, then High, Medium, Low, then No priority.
2. **Manual order** — the position the owner set by dragging in the Linear UI.
3. **Size, biggest first** — the estimate, largest first, so the heavy work starts earliest rather than being left until capacity is gone.

Do not substitute "quickest first". Starting with the small items feels productive and leaves the
expensive work stranded at the end of a session.

Known gap to be honest about: the Linear MCP's `list_issues` exposes `orderBy` for `createdAt` and
`updatedAt` only, and its results carry `priority` but not the manual `sortOrder`. So priority is
sortable directly, size is sortable when estimates are set, and manual order has to be read from the
Linear UI or supplied by the owner. Say which keys were actually available rather than implying a
full sort happened.

### One issue per unit of work

- If it warrants an OpenSpec change, it warrants a Linear issue; the two are one-to-one. Edits to
  agent instruction files, editor config, and other pure process changes need neither.
- Work reported in chat gets an issue **before** work starts, not after.
- Record the request in the reporter's own words. Quote verbatim where the wording is ambiguous or
  contains an obvious typo, and note the interpretation as a separate remark rather than silently
  correcting it — the raw report is evidence, the reading is opinion.
- One issue = one independently verifiable defect or capability. An issue that turns out to contain
  two gets split into sub-issues, so its status can mean something.
- Every issue carries exactly one of `Bug` / `Feature` / `Improvement` and is assigned to the person
  who owns the outcome. Agents do not own issues.
- Nothing is dropped silently: use `Canceled` or `Duplicate`, with a comment saying why.

### Status changes follow real events, not intentions

- **Todo → In Progress** when the branch and worktree exist and work has begun — not when the work
  is discussed or planned.
- **In Progress → Done** means **ready for the owner's testing**: the change is merged into the
  integration branch, the full check set passes on the merged tip, the OpenSpec change is archived,
  and the branch is pushed. `Done` is not a claim that a human has exercised the feature — the owner
  does manual testing after, and the rule of thumb is that if it was good enough to push, it is
  `Done`. A delegated agent reporting success is still not enough: the orchestrating agent verifies
  the merged tip itself.
- Drive the feature in the running app wherever it is practical, and say in the finishing comment
  exactly what was and was not exercised — an unverified path named plainly is useful, whereas
  withholding `Done` until every path has been clicked just hides finished work behind a status.
- Blocked work moves back to `Todo` with a comment naming the blocker. It does not sit in
  `In Progress` where it reads as active.

### Names tie Linear, git, and OpenSpec together

- Branch names contain `dra-<n>` so Linear links them automatically. Linear's suggested branch name
  is fine, shortened if unwieldy.
- Worktree directory: `wt-dra<n>`.
- Squash commit subject ends with ` (DRA-<n>)` — still a single line, still no AI attribution.
- OpenSpec change directory: `dra-<n>-<slug>`.
- The PR body lists one `Fixes DRA-<n>` line per issue in the batch.

### Comments are the record

Post to the issue at three moments, and not per commit:

1. **Starting** — branch, worktree, OpenSpec change path, and how the request was read, including
   assumptions and anything found ambiguous.
2. **Finishing** — the squash commit SHA, what changed per service and file, test counts before and
   after, how it was verified end-to-end (what was actually driven in the running app), the archived
   spec path, and explicitly what was left out of scope.
3. **Deviating** — scope changes, blockers, findings that belong to a different issue (link it), and
   earlier conclusions that turned out to be wrong.

- Record failures and dead ends too. An issue history containing only successes is not a source of
  truth, and the next person repeats the dead end.
- Evidence, not adjectives: SHAs, paths, counts, commands. "Fixed and tested" records nothing.
- Attach screenshots and recordings to the issue; they do not belong in the repo working tree.

### Delegation

- Only the orchestrating agent writes to Linear. Delegated agents report back to it and never
  comment on issues themselves: a worktree agent cannot see the merged result or the sibling issues,
  and parallel writers interleave half-truths on the same issue.
- Hand a delegated agent the issue text verbatim, not a summary of it.

### Batches

- A batch of issues shares one integration branch; each issue gets its own worktree branch off it
  and is squash-merged back as a single commit. The PR is opened from the integration branch.
- Issues reach `Done` on merge into the integration branch. The PR landing on `main` is tracked on
  the PR itself, not as a second status hop.

### When Linear is unreachable

Do the work, say plainly in the final report that it was not recorded, and write the missing
comments once Linear is reachable again. Never let the chat log become the record by default.

## Keep the Surrounding Files Current

A change is not finished when the code works. Every change must also update whatever else it made
stale — in the same change, not as a follow-up:

- **`README.md`** (root and the service's own) — setup steps, service URLs and ports, test commands,
  and any list that enumerates the services.
- **OpenTelemetry configuration** — a service that emits no telemetry is invisible in production.
  Adding or renaming a service means wiring its tracing, metrics, and logs the same way the existing
  services do, reusing the shared setup helper rather than hand-rolling per-service bootstrap.
- **Docker and infrastructure configuration** — `docker-compose.yaml`, the service `Dockerfile`,
  `.env.example` files, and anything that derives the infra service list.
- **Scripts and make targets** — `scripts/*.sh` and any equivalent make targets, especially the ones
  that enumerate services to lint, test, build, or start. A script with a hardcoded service list is a
  place a new service gets silently omitted.
- **Swagger / API index** — `services/dashboard/features/swagger/lib/openapi.ts`, and any other
  page that lists endpoints or services.

The recurring failure this prevents: a service is added, its code works, and it is quietly missing
from the telemetry stack, the API index, and half the scripts — each omission found weeks later as a
separate bug. When a change touches the set of services, or a port, or a required environment
variable, grep for the *existing* services by name to find every list that will need the new one too,
and say in the final report which ancillary files you updated.

## Repo Conventions

- Use `scripts/test.sh unit` for unit tests.
- Use `scripts/test.sh integration` for integration tests when the Docker stack is running.
- Use `scripts/docker.sh build` when a rebuild is needed.
- Follow existing structure inside each service instead of forcing one pattern across the monorepo.

## Driving the System End-to-End

This section is for **you**, an agent changing this repository, not for a person playing
the game. It is the loop that lets you verify your own change instead of reporting "the
unit tests pass" and hoping: create a game, start a player agent on it, read what the
agent actually did, read the live board, ask the judge to grade it, read the verdict.

Every service exposes its whole HTTP API over MCP at `/mcp`, and `.mcp.json` registers
all four servers, so the loop is tool calls rather than hand-written `curl`. **An MCP
tool's name is its endpoint's `operation_id`** — `create_game`, `submit_prompt`,
`list_game_events`, `list_game_rounds` — and a client normally prefixes it with the
server name, so the same tool appears as `game-service_create_game` to the game-playing
agent and as `create_game` under the `game-service` server to you. When a tool you
expect is missing, the route was deliberately excluded (see *What is not a tool*); the
HTTP endpoint still works.

### 0. Prerequisites, and the four things that waste an afternoon

**Initialise submodules in a new worktree.** `git worktree add` does **not** populate
them, and nothing warns you:

```bash
git submodule update --init --recursive
```

`external/dragncards` and `external/dragncards-mc-plugin` come up empty otherwise, and
game-service's typed-action registry is generated from the plugin JSON at import time —
with no JSON, the generated `Literal` collapses to `Literal[()]` and the game-service
suite fails with roughly 384 collection errors that look nothing like a missing
submodule. Check `ls external/dragncards-mc-plugin/json` returns files before running
anything.

**Start infrastructure, and know what "infrastructure" means.**

```bash
./scripts/docker-infrastructure.sh start   # DragnCards, the databases, Valkey, Bifrost, otel-lgtm
make run                                   # the five app services, from source, on top of it
```

Ports: dashboard `3001`, game-service `4001`, agent-orchestrator `4002`, bifrost `4003`,
history-service `4004`, eval-service `4005`, Grafana `3004`, DragnCards frontend `3000`
and backend `4000`.

**Confirm the running services match your source before you conclude anything.** A
Compose stack that was started before your change is serving the old image, and a missing
endpoint then looks like a bug in your reasoning rather than a stale container. The cheap
check is to diff the live route list against the routers you just edited:

```bash
curl -s http://localhost:4005/openapi.json | python3 -c 'import sys,json; print(sorted(json.load(sys.stdin)["paths"]))'
```

If a route you can see in `services/*/src/*/api/routers/` is absent from that list, the
container is old: `./scripts/docker.sh build` and restart it, or run that one service
from source. This is not hypothetical — it is the normal state of a long-running local
stack.

**Configure the judge before you get to step 5.** eval-service needs a judge model and a
judge API key, and it fails *every* target without them rather than refusing the request
up front. Check first, and treat `degraded` as a blocker for the evaluation step:

```bash
curl -s http://localhost:4005/ready     # {"status":"degraded", …, "judge_configured":false} == not ready
```

`EVAL_JUDGE_MODEL` has no default. The key is per provider and named
`EVAL_JUDGE_<PROVIDER>_API_KEY` (`EVAL_JUDGE_OPENROUTER_API_KEY` for OpenRouter) so the
judge bills to its own budget under the `eval-judge` Bifrost identity — it must never
fall back to a game-playing key. Set these in your environment or a local `.env`, never
in a committed file.

### 1. Create a game

`create_game` on **game-service**, body `{"plugin_name": "marvel-champions"}` — both
fields default, so `{}` works too. Keep `session.session_id` from the response: it is the
id every later game-service call takes, **and** it is the `game_id` history-service and
eval-service key on. Do not pass `ephemeral: true`: an ephemeral session emits no history,
so nothing downstream of step 3 will exist.

Then set the table up, in this order:

1. `set_player_count_action` — `{"type": "set_player_count", "num_players": 1, "layout_id": …}`.
   Read the valid `layout_id` values from `get_session_actions` →
   `plugin_metadata.player_count_layouts[].layout_id`; they are generated from the plugin
   JSON, so they are not in the Python source.
2. `search_prebuilt_sets_marvel_champions` with `name=` to resolve deck ids — never
   hardcode a deck UUID.
3. `load_prebuilt_deck` once per hero, **then** the villain/scenario set. `deck_id` is a
   **query parameter**, not a body field. The wrong order fails with "Load all player
   decks before loading the scenario".
4. `mulligan_draw_hand` per seat, `{"type": "mulligan_draw_hand", "player_n": "player1"}`.

**Worked?** `get_game_state` returns a `state` with populated `zones` and a `players` entry
for each seat. Open `http://localhost:3000/room/<room_slug>` to see the same table.

### 2. Start a player agent on it

On **agent-orchestrator**:

1. `create_session` — every field is optional, `{}` is valid. Keep `session.id`.
2. `list_providers` — pick an entry with `available: true` and a non-empty `models`, then
   `set_session_model_config` with `{"provider_id": …, "model_name": …}` taking
   `model_name` verbatim from that list (it already carries the provider prefix).
3. `enable_session_skill` with `{"skill_name": "marvel-champions-play"}`. Skill names are
   the directory names under the repo-root `skills/`.
4. The game-service MCP server is already attached: a non-custom registry entry is seeded
   at startup and every new session enables it. Confirm with `list_session_mcps`, and
   confirm the tools resolved with `list_session_tools` — you should see
   `game-service_*` names.
5. `submit_prompt` with `{"prompt": …}`. Returns `202` and a `job.id`.

**Nothing binds a session to a game, and this is the step agents get wrong.** There is no
"attach session to game" endpoint. The agent learns its game and its seat *only from your
prompt text*, so the prompt must state the game-service `session_id`, the hero, and the
seat (`player1`). `session.metadata.game_id` is then populated automatically from the
agent's first game-service tool call, and that is what stamps the history events — so an
agent that never calls a game-service tool records nothing under the game.

**Worked?** `get_job_status` moves off `queued`, and `list_job_events` starts returning
`tool_call` events whose `assignment` is `game-service`.

### 3. Analyse what the agent did

`list_job_events` on agent-orchestrator, `{"after": <last id seen>}` — ascending,
`after` exclusive, so poll by advancing the cursor. Prefer this over
`stream_job_events`: the SSE endpoint is not an MCP tool (a tool call reads its response
to completion and a stream never completes).

The events worth reading: `tool_call` carries `tool_name` (the real name),
`exposed_tool_name` (what the model saw), `assignment` (the MCP server) and `arguments`;
`tool_result` carries the matching `tool_call_id`, `is_error` and `result`. `reasoning`
and `model_output` show what the model was thinking between calls.

**Know when it stopped.** `completion`, `failure` and `cancellation` are the only terminal
events. Poll `get_job_status` as the authority: terminal statuses are `completed`,
`failed`, `cancelled` and `interrupted`. Note the asymmetry — hitting the tool-round limit
emits a `completion` event but leaves the job `interrupted`, so an agent that only watches
events concludes success from a truncated run.

### 4. Fetch the live board state

`get_game_state` on game-service. For Marvel Champions the response is the *simplified*
state — the same view the playing agent sees — with top-level `roundNumber`, `mode`,
`villainHitPoints`, `stepId`, `stepDescription`, `players` and `zones`. Face-down cards and
deck contents collapse to a single `HIDDEN` entry carrying a `stackSize` count.

`stepId` gives the phase, not the acting player: whose turn it is is not a field anywhere,
and the orchestrating prompt tracks it. `mode` is `unknown | in progress | win | loss`.

`GET /games/{id}/state/raw` exists for the rare case where you need DragnCards' own
structure, and is deliberately HTTP-only: it is ~450 KB per game, about half of it the
engine's `deltas` undo log, and putting that in a context window is never what you wanted.

### 5. Invoke the evaluation agent

Recording is asynchronous, so first confirm the game reached the event store:
`list_recorded_games` on **history-service** returns `games[]` ordered by most recent
activity, with `game_id` equal to the game-service session id and an `event_count`. Read
the ordered transcript with `list_game_timeline` (pruned payloads, up to 5000) or
`list_game_events` (full payloads, up to 1000 — tens of MB for a real game); both page on
`after_seq` and you follow `next_after_seq` until it is absent.

Then on **eval-service**:

1. `list_game_rounds` → `rounds[]` with `round_number` (1-based round *of play*),
   `from_seq`, `to_seq`, `move_count` and the `players` who acted. A `404` here means the
   game has no recorded events — go back to step 2 and check `metadata.game_id`.
2. `create_evaluation` with `{"scope": "round", "selection": {"rounds": [1]}}`. `scope` is
   `move`, `round` or `game`; `selection` needs at least one of `rounds`, `seqs`,
   `seq_range` or `whole_game`. There is no `player` field — attribution is derived from
   the recorded moves, and a round request fans out to one target per acting player. Pass
   `"force": true` to re-grade something already judged. Keep `request_id`.

Select rounds by number rather than picking a single action: a Marvel Champions play is
normally several recorded events (play the card, exhaust to pay, assign the damage), and
grading one of them alone marks a good play down once per event.

### 6. Read the verdict

`get_evaluation` with the `game_id` and `request_id`. **It is done when `status` is
anything other than `pending`** — then `completed`, `partial`, `failed` or `cancelled`.
The verdicts are in this response: each `targets[]` entry carries `player`, `target_seq`,
`round_span`, a per-target `status`, and a `verdict` with `overall_score`, the four
`scores` (`rules_legality`, `strategic_quality`, `tempo_efficiency`, `threat_resource`),
a `rationale`, `flags` and the `evaluator` identity.

Read the per-target `status` before the score. `skipped` means the action held no decision
to grade and is **not** a bad verdict; `failed` is a real error whose reason is on `error`
— and every target `failed` with the judge unconfigured is exactly the prerequisite from
step 0.

Verdicts are also written back to history-service as events with `actor: "evaluator"` and
`event_type: "evaluation"`, so `list_game_events` filtered on that pair is the durable
copy if you want the verdict alongside the moves it grades.

### Clean up after yourself

The stack is shared. `delete_game` on game-service and `terminate_session` /
`delete_session` on agent-orchestrator remove what you created. Say in your report which
games and sessions you created on a stack you do not own — a stray running session keeps
spending tokens.

### What is not a tool, and why

Excluding a route removes it from MCP only; the HTTP endpoint is untouched, so nothing here
limits the dashboard or a deliberate `curl`. Three kinds are kept out of every service's
surface, and `dragncards_common.mcp` is where the rule lives:

- **Liveness and readiness probes**, for every service — noise in a tool list.
- **Server-sent event streams** — `stream_job_events`, `stream_evaluation`,
  `export_game_bundle`. A tool call reads its response to completion; these do not
  complete, or complete only by handing back an entire recorded game. Poll the paged read
  next to them instead.
- **Irreversible destruction and deployment-global mutation** — deleting a game's whole
  recorded history, backfilling or importing events into the ordered store, bulk-clearing
  the evaluation queue, and editing the shared skill / MCP / persona registries. These change state
  for every session in the deployment, including the owner's. game-service set this
  precedent by keeping its snapshot import/export, room-control and raw-DragnLang routes
  on HTTP only.

Per-session and per-object cleanup stays available on purpose, so an agent can always undo
its own work.

### Checks, and what is safe to run against a live stack

```bash
./scripts/lint.sh --fix
./scripts/test.sh unit                        # no network needed
./scripts/test.sh integration <service>       # safe against a running instance
openspec validate --all
```

`scripts/test.sh integration` is safe against a live deployment because its fixtures create
a throwaway `*_test_<uuid>` database per run and drop it at the end, so the suite never
touches the data the running services are using. Naming one service keeps the run short.

`openspec validate --all` reports **exactly one** pre-existing failure,
`spec/typed-game-actions`, on `main` and on every branch off it. One failure is the expected
result; two means you caused one.

## Adding or Changing a Service

**README, OpenTelemetry configuration, Docker/infrastructure configuration, and the
`Makefile`/`scripts/` entries are kept current by whatever change requires it.** They are part
of that change, not follow-up work: a change that leaves them stale has left the repository
describing a system that no longer exists.

A service is also not finished when its own code works. A fixed set of files enumerates
services, and a service missing from one of them is broken in a way its own tests cannot
detect. DRA-23 is the worked example: `history-service` and `eval-service` shipped with their
`OTEL_*` variables set in `docker-compose.yaml` and **zero** OpenTelemetry code anywhere in
`src/` or `docker/`, so every easily inspected surface looked correct while the two services
exported nothing at all for their whole existence.

Work through this list when adding a service, and re-check the affected entries when changing
one:

- **Telemetry, in code — not only in configuration.** Setting `OTEL_*` environment variables
  wires nothing on its own. A new Python service MUST: depend on `dragncards-common`; add a
  `src/<service>/telemetry.py` that binds its own `DEFAULT_SERVICE_NAME` to
  `dragncards_common.telemetry`; call `setup_telemetry()` in its entrypoint *before* the app
  is built; call `instrument_fastapi_app(app)` in its app factory and `shutdown_telemetry()`
  in the lifespan teardown; call `instrument_sqlalchemy_engine(engine)` inside `create_engine`
  if it has a database; and pass `get_tracer(__name__)` into the shared `RespConnection` if it
  talks to Valkey — that client is silent unless it is handed a tracer. Add manual spans
  around the repo-specific workflows generic library instrumentation cannot explain. Do NOT
  write a fresh per-service bootstrap: `game-service` predates the shared helper and keeps its
  own equivalent copy, and a third copy is how the pattern drifts apart. Set
  `OTEL_SDK_DISABLED=true` in the test root `conftest.py` so the suite starts no exporters.
- **Prove the wiring with a test, not by inspection.** Each service has a
  `tests/unit/test_telemetry.py` asserting its identity, that the entrypoint initialises
  telemetry, and that each edge it owns is instrumented. That is the check the missing
  instrumentation would have failed.
- **Never put a request body, prompt, model response, recorded game state, or credential on a
  span attribute.** Spans carry identifiers, scopes, counts and outcomes. Telemetry leaves the
  process and the collector is readable by anyone who can reach it, so a span attribute is a
  real exfiltration path — pin the permitted attribute keys in a test rather than trusting
  review.
- **`docker-compose.yaml`**: the service definition and port mapping, its `OTEL_SERVICE_NAME`,
  `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL` and `OTEL_RESOURCE_ATTRIBUTES`,
  and a `depends_on` entry for `otel-lgtm` with `condition: service_healthy`.
- **`services/<service>/.env.example`**: every setting the service reads, with placeholder
  values only, including the commented OpenTelemetry block for a direct local run. Never a
  real key, token, or connection secret in a committed file.
- **`scripts/service-helpers.sh`**: `list_services`, `service_test_command`,
  `service_start_command`, and `service_http_port`.
- **`scripts/lint.sh`**: the per-language loop that formats and checks the service.
- **The dashboard's service set — one declaration, no second list.**
  `services/dashboard/features/proxy/lib/proxy.ts` holds `SERVICE_KEYS`, the single declaration
  of which first-party services the dashboard fronts; `ServiceKey` is derived from that array,
  and the `/api/proxy/[service]` route, the upstream base-URL lookup, and the merged Swagger
  index in `services/dashboard/features/swagger/lib/openapi.ts` are all keyed by it. Adding a
  service is: its key in `SERVICE_KEYS`, its base URL and OpenAPI path in
  `services/dashboard/features/config/lib/dashboard-config.ts` (plus
  `services/dashboard/vitest.setup.ts`, which clears every variable the config reads), then
  fixing the `Record<ServiceKey, …>` type errors that follow. Never write a second list of
  services beside `SERVICE_KEYS`, and never iterate a literal array of service names. DRA-20 is
  the worked example: the merge looped a hardcoded `["orchestrator", "game"]` and branched
  two-way for the upstream URL, so `history-service` and `eval-service` were reachable through
  the proxy yet entirely absent from `http://localhost:3001/swagger` — `history` was already a
  valid `ServiceKey` with a path prefix, and its document was simply never fetched. Confirm the
  new service actually serves a document (all four are FastAPI apps serving `/openapi.json`) and
  configure its path if it differs, rather than adding an index entry whose fetch fails.
- **`README.md`**: the service URL table, the architecture diagram, the prose describing what
  the service does, the Swagger playground note, and the Observability section if the wiring
  changed.
- **`AGENTS.md`**: this file's *Useful Reading* and *Service-Level Guides* lists, plus a
  `services/<service>/AGENTS.md` of the service's own.
- **`openspec/specs/`**: the capability spec that now covers the service — including
  `observability`, whose requirements name the services they apply to. A requirement that does
  not name a service does not constrain it, which is exactly how the omission above survived
  review.

## Data Storage

- Services must NOT store any state in memory.
- Use PostgreSQL for persistent data.
- Use Valkey for ephemeral/stateful data that doesn't require persistence.

## Agent Guidance

- Start by reading `README.md` and the files closest to the requested change.
- When working in `openspec/`, preserve the existing OpenSpec workflow and artifact format.
- When working in `external/`, treat vendored or upstream code carefully and avoid unnecessary edits.
- Explain assumptions briefly when behavior is ambiguous.
- Before finishing a task, you are expected to run:
  - `./scripts/lint.sh --fix`
  - `./scripts/test.sh unit`
  - `./scripts/docker-infrastructure.sh start` followed by `./scripts/test.sh integration`
