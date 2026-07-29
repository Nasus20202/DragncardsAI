# Give every service an MCP surface and document the agent debug loop (DRA-24)

## Why

The issue (DRA-24) asks for two things:

> - The coding agent should be able to use MCP in the services to fetch data about the
>   game for debugging.
> - A whole flow should be documented for the coding agent: create a game, start a player
>   agent in DragncardsAI, analyze the agent actions, fetch the live state of the boards,
>   invoke the evaluation agent, etc.
> - This flow will allow the agent to test the change autonomously

The second bullet is the goal; the first is what makes it possible. So the work started as
a gap analysis of what an agent could already do, service by service.

**game-service was already fully driveable over MCP.** It mounts a FastMCP server at
`/mcp` built with `FastMCP.from_fastapi`, `.mcp.json` registers it, and a read-only
`list_games` call against the running instance returns `{"sessions":[]}`. Creating a game,
loading decks, reading the simplified board state and running any typed action are all
tool calls today. Nothing needed adding there, and nothing was.

**The other three services had no MCP surface at all.** `GET /mcp/` returned `404` on
ports 4002, 4004 and 4005 against the running stack, against `406` on 4001 (the correct
streamable-HTTP response to a bare GET, i.e. mounted). Four of the six steps the issue
names — start a player agent, analyse its actions, invoke evaluation, read the verdict —
live entirely outside game-service. An agent could still reach them with `curl`, but with
no tool schemas it had to guess request shapes from source every time, which is exactly
the "needlessly hard" the issue is about. `agent-orchestrator` has an
`integrations/mcp/` package, which reads as MCP support until you notice it is the
*client* it uses to hand game-service tools to the game-playing agent — the opposite
direction from what a coding agent needs.

**Generated tool names were unusable even once mounted.** These three services set no
`operation_id` on any route, so FastAPI generated
`submit_prompt_sessions__session_id__prompts_post` and FastMCP truncated it to a lossy,
collision-prone `restore_game_games`. A tool list is the entire discoverability surface
for an agent; `list_games_games_get` and `restore_game_games` are not a usable one.

**And the flow was not written down anywhere.** Four traps in particular are discovered
rather than read, and each one costs an afternoon:

- `git worktree add` does not populate submodules. `external/dragncards` and
  `external/dragncards-mc-plugin` come up empty, game-service's typed-action registry is
  generated from the plugin JSON at import time, the generated `Literal` collapses to
  `Literal[()]`, and the suite fails with ~384 collection errors that look nothing like a
  missing submodule.
- **A long-running local stack serves older images than the source.** Verified while
  writing this: the running agent-orchestrator had no `/personas` or `/players` routes and
  the running eval-service had no `/games/{game_id}/rounds`, all three of which exist in
  the branch source. An agent that trusts the live stack concludes an endpoint does not
  exist.
- eval-service fails *every* evaluation target when no judge is configured rather than
  refusing the request. `GET :4005/ready` on the running stack reports
  `{"status":"degraded", …, "judge_configured":false}`, so the evaluation step of the loop
  is blocked before it starts. `EVAL_JUDGE_MODEL` has no default and the key is per
  provider (`EVAL_JUDGE_<PROVIDER>_API_KEY`).
- `openspec validate --all` has exactly one pre-existing failure,
  `spec/typed-game-actions`. Without knowing that, an agent either chases it or stops
  trusting the command.

## What Changes

- **The MCP surface becomes shared, once.** `dragncards_common.mcp` owns building a
  FastMCP server from a service's own FastAPI OpenAPI schema and mounting its
  streamable-HTTP transport at `/mcp`, wrapping the app's existing lifespan with
  `combine_lifespans` so the MCP session manager starts and stops with the service. It
  always excludes `/health` and `/ready`, and takes each service's own exclusion list —
  either a path regex or `(path_regex, methods)`, because one path is often a safe read and
  an unsafe write. `game-service` keeps its own equivalent copy, exactly as it keeps its own
  telemetry bootstrap, and both `AGENTS.md` files say so, so the duplication is not read as
  an accident.
- **agent-orchestrator, history-service and eval-service each mount their own surface** via
  a thin `mcp_server.py` that declares only what it keeps out. The mount happens in
  `main.py` and deliberately not in the app factory: the test suites build the app directly
  and must not start an MCP session manager.
- **Tools are generated, never hand-written.** There is no place in this design to add a
  tool that is not an endpoint. A hand-written tool layer would be a second implementation
  of the API free to drift from the first, and the MCP-vs-HTTP consistency rule in
  `services/game-service/AGENTS.md` would become something a reviewer had to enforce by
  eye.
- **Every route on the three services gains an explicit `operation_id`** — 65 of them — so
  the MCP tool names are `create_session`, `submit_prompt`, `list_job_events`,
  `list_game_rounds`, `get_evaluation` rather than FastAPI's generated forms. This also
  improves the dashboard's Swagger index, which prefixes and displays `operationId`.
- **The exclusion list is treated as the security surface, because it is.** These services
  have no authentication, so anything left in the surface is something a model can invoke
  on a running deployment. Three classes are kept out: probes (noise); server-sent event
  streams and the streaming bundle export (a tool call reads its response to completion,
  and these either never complete or complete by handing back a whole recorded game); and
  irreversible or deployment-global operations — deleting a game's recorded history,
  backfilling or importing events into the ordered store, bulk-clearing the evaluation
  queue, and writing the shared skill, MCP and persona registries. Per-session and
  per-object cleanup stays exposed on purpose, so an agent can always undo its own work.
  Exclusion removes a route from MCP only; every one still works over HTTP.
- **The loop is documented where an agent will actually read it.** A new *Driving the
  System End-to-End* section in the root `AGENTS.md` walks the six named steps with the
  real tool names, the real required fields, and — for each step — what to check to know it
  worked. It opens with the four prerequisites above, including how to detect a stale stack,
  and closes with which checks are safe to run against a live deployment and why
  (`scripts/test.sh integration` fixtures create a throwaway `*_test_<uuid>` database and
  drop it) and the one expected `openspec validate` failure.
- **The documentation records what the source does not.** Two findings that cost real time:
  nothing binds an orchestrator session to a game — the agent learns its game id and its
  seat *only* from the prompt text, and `session.metadata.game_id` is populated from its
  first game-service tool call — and a job that hits the tool-round limit emits a
  `completion` event while ending with status `interrupted`, so watching events alone reads
  a truncated run as a success.
- **Ancillary files brought current**: `.mcp.json` registers all four servers; the root
  `README.md` service table gains an MCP endpoint column and a new *MCP surfaces* section;
  each of the four services documents its own surface and exclusions in its `AGENTS.md` and
  `README.md`; `openspec/config.yaml` records both the shared MCP bootstrap and that
  agent-orchestrator is now an MCP server as well as a client.

## Non-goals

- **No new MCP tools, and no second MCP server.** game-service's surface is untouched;
  every tool on the other three services is an endpoint that already existed. The only
  behavioural change to an existing endpoint is its `operation_id`.
- **No authentication on the MCP endpoints.** These are localhost development services and
  adding an auth scheme to four services is its own change; the exclusion list is what
  bounds the blast radius today, and the reasoning is written down so the next person can
  reopen it deliberately.
- **No migration of `game-service` onto the shared helper.** It is the only Python service
  without a `dragncards-common` dependency and its image installs from its own lockfile
  with `uv sync --frozen`, so migrating it means a dependency plus a Dockerfile change that
  cannot be verified without building the image — the same reason DRA-23 left its telemetry
  bootstrap alone. Deliberately deferred and recorded in both `AGENTS.md` files.
- **No end-to-end integration test of the whole loop.** There is none today: the
  eval-service integration tests stub the history client and `services/smoketest` covers
  only dashboard → orchestrator → `create_game`. Writing one needs a full stack this change
  was not permitted to start or restart, and it is a testing-capability change rather than
  an MCP one.
- **No fix for the stale running stack.** That is a property of the owner's local
  deployment, not of the repository. The change documents how to detect it and what to do
  about it.

## Capabilities

### New Capabilities

- **service-mcp-surface**: every first-party backend service exposes its HTTP API as MCP
  tools generated from its own OpenAPI schema, under a declared per-service exclusion
  policy, and the end-to-end loop those surfaces exist for is documented for an agent
  verifying its own change. This is a genuinely new area: the `game-service` capability
  enumerates that service's individual tools, and no existing requirement says anything
  about the other three services having an MCP surface, how tools are derived, or what must
  never become one.

### Modified Capabilities

None. No existing requirement changes meaning. game-service's spec enumerates its tools by
name and those names are unchanged; the new requirements sit alongside it and constrain how
a surface is built rather than which tools game-service has.

## Impact

- **Production code**:
  - `services/shared/src/dragncards_common/mcp.py` (new — the shared bootstrap)
  - `services/shared/src/dragncards_common/__init__.py`, `services/shared/pyproject.toml`
    (FastMCP as a dependency, FastAPI as a test-only one)
  - `services/agent-orchestrator/src/agent_orchestrator/mcp_server.py` (new)
  - `services/history-service/src/history_service/mcp_server.py` (new)
  - `services/eval-service/src/eval_service/mcp_server.py` (new)
  - `services/{agent-orchestrator,history-service,eval-service}/src/*/main.py` (mount)
  - `services/agent-orchestrator/src/agent_orchestrator/api/routers/{catalog,context,jobs,meta,personas,players,sessions}.py`,
    `services/history-service/src/history_service/api/routers/{events,games,meta,restore,snapshots,transfer}.py`,
    `services/eval-service/src/eval_service/api/routers/{evaluations,meta}.py`
    (explicit `operation_id` on all 65 routes)
- **Tests**: `services/shared/tests/test_mcp.py` (new),
  `services/{agent-orchestrator,history-service,eval-service}/tests/unit/test_mcp_server.py`
  (new), and the entrypoint-order assertion in each of those services'
  `tests/unit/test_telemetry.py` extended to cover the mount.
- **Configuration**: `.mcp.json`.
- **Documentation**: `AGENTS.md`, `README.md`, `openspec/config.yaml`, and the `AGENTS.md`
  and `README.md` of `game-service`, `agent-orchestrator`, `history-service` and
  `eval-service`.
- **Database**: none.

## Notes

The MCP transport is verified end to end, over real HTTP, but only for one of the three
services. eval-service was started from source on a spare port against a throwaway SQLite
database, and a full streamable-HTTP MCP session was driven against it: `initialize`
returned a session id, `tools/list` returned exactly the six expected tools with their new
readable names, `tools/call` on `list_evaluations` executed the real handler and returned
`{"requests":[]}`, and `tools/call` on the excluded `stream_evaluation` returned
`Unknown tool`. agent-orchestrator and history-service are verified by unit test against
their real applications, not over the wire, because bringing them up would have meant
either restarting the owner's stack or running a second history-service ingester that would
consume events from the shared Valkey stream out from under the running one. What remains
for the orchestrator to confirm after merge is recorded in `tasks.md` section 8.
