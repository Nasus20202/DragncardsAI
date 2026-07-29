# Tasks

## 1. Establish what already worked before adding anything

- [x] 1.1 Confirm `game-service` already exposes a full MCP surface: `mcp/server.py` builds
      it with `FastMCP.from_fastapi`, `main.py` mounts it at `/mcp`, `.mcp.json` registers
      it, and a read-only `list_games` call through the configured server against the
      running instance returns `{"sessions":[]}`. Nothing to add, and nothing added.
- [x] 1.2 Confirm the other three services had no MCP surface: `GET /mcp/` returns `404`
      on ports 4002, 4004 and 4005, against `406` on 4001 — the correct streamable-HTTP
      rejection of a bare GET, i.e. mounted.
- [x] 1.3 Confirm `agent_orchestrator/integrations/mcp/` is the MCP *client* (it attaches
      game-service tools to a session for the game-playing agent), not a server, so the
      service's existing "MCP" support is the opposite direction from the one the issue
      needs.
- [x] 1.4 Map each of the six steps in the issue to the service that owns it: step 1 and
      step 4 are game-service (already driveable), steps 2, 3, 5 and 6 are
      agent-orchestrator, history-service and eval-service (not driveable).
- [x] 1.5 Enumerate the real route list of all four services from source and from each
      running instance's `/openapi.json`, so the exclusion regexes match real paths.
- [x] 1.6 Confirm no `operation_id` is set anywhere on the three services, and measure the
      consequence: the generated surface names tools `list_games_games_get` and
      `restore_game_games` (FastMCP truncating FastAPI's generated identifiers).
- [x] 1.7 Confirm the dashboard does not generate a client from any OpenAPI schema —
      `features/swagger/lib/openapi.ts` only prefixes `operationId` for display — so
      renaming operations breaks no consumer.
- [x] 1.8 Confirm `dragncards_common` offered no MCP helper: the only implementation was
      inside `game-service`.

## 2. Shared bootstrap in dragncards-common

- [x] 2.1 Add `dragncards_common/mcp.py`: `MCP_MOUNT_PATH`, `ALWAYS_EXCLUDED_ROUTES`,
      `ExcludedRoute`, `_route_maps`, `build_mcp_server`, `mount_mcp_server`.
- [x] 2.2 Support method-level exclusion (`(pattern, methods)`) alongside a bare path
      regex, because history-service's `/games/{game_id}/events` is a safe `GET` read and
      an unsafe `POST` write on one path.
- [x] 2.3 Exclude `/health` and `/ready` for every service, non-overridably.
- [x] 2.4 Compose lifespans with `combine_lifespans` rather than replacing the app's, so
      the service's own startup still runs.
- [x] 2.5 Declare `fastmcp` in `services/shared/pyproject.toml`, and `fastapi` as a
      test-only dependency — the module itself never imports FastAPI, so the library does
      not acquire that dependency for its consumers.
- [x] 2.6 Record the reasoning for each class of exclusion in the module docstring, since
      that is what the next person adding a service will read.
- [x] 2.7 Cover it in `services/shared/tests/test_mcp.py`: probes excluded, tools named
      after operation identifiers, path-only and method-level exclusion, the HTTP endpoint
      surviving an MCP exclusion, the mount adding the transport and wrapping the lifespan,
      and the probe exclusions being non-overridable.

## 3. Mount a surface on each of the three services

- [x] 3.1 Add `agent_orchestrator/mcp_server.py`: name, exclusion list, `mount`.
- [x] 3.2 Add `history_service/mcp_server.py`: name, exclusion list, `mount`.
- [x] 3.3 Add `eval_service/mcp_server.py`: name, exclusion list, `mount`.
- [x] 3.4 Call `mount_mcp(app)` from each service's `main.py` after `create_app`, with a
      comment saying why it is not in the factory (the suites build the app directly and
      must not start an MCP session manager).
- [x] 3.5 Register all four servers in `.mcp.json`.

## 4. Make the tool names usable

- [x] 4.1 Add an explicit `operation_id` to all 44 agent-orchestrator routes.
- [x] 4.2 Add an explicit `operation_id` to all 11 history-service routes.
- [x] 4.3 Add an explicit `operation_id` to all 10 eval-service routes.
- [x] 4.4 Verify per service that every operation identifier is unique and that no
      framework-generated name remains, by probing the built OpenAPI schema.

## 5. Draw the exclusion line deliberately

- [x] 5.1 Exclude the server-sent event streams: `stream_job_events`,
      `stream_evaluation`. A tool call reads its response to completion; these do not
      complete.
- [x] 5.2 Exclude `export_game_bundle`: it completes only by returning an entire recorded
      game as NDJSON.
- [x] 5.3 Exclude irreversible destruction — `delete_game_history` — and the writes into
      the ordered event store, `backfill_game_event` and `import_game_bundle`.
- [x] 5.4 Exclude the deployment-global registry and persona writes — `register_skill`,
      `unregister_skill`, `register_mcp`, `unregister_mcp`, `save_persona`,
      `delete_persona` — while keeping every corresponding read exposed.
- [x] 5.5 Exclude `clear_evaluations`, an unscoped bulk delete across the deployment, while
      keeping `delete_evaluation` for one request so an agent can still clean up after
      itself.
- [x] 5.6 Keep per-session and per-object lifecycle exposed on purpose:
      `terminate_session`, `delete_session`, `disable_session_skill`, `remove_session_mcp`,
      `delete_evaluation`. A surface that can only create is worse on a shared stack.
- [x] 5.7 Correct the `clear_evaluations` comment after review: the endpoint removes only
      *fully-terminal* requests and never touches history write-backs, so "deletes every
      evaluation" overstated it. The reason it stays excluded is that its scope is the
      whole deployment rather than the caller's own requests.
- [x] 5.8 Add `tests/unit/test_mcp_server.py` per service asserting against the real
      application's tool list — the loop's tools present, the excluded ones absent — rather
      than against the exclusion list, because a pattern matching nothing is
      indistinguishable from one that works.
- [x] 5.9 Extend each service's entrypoint-order assertion in `tests/unit/test_telemetry.py`
      to `["setup_telemetry", "create_app", "mount_mcp", "run"]`, so removing the mount from
      `main.py` breaks a test.

## 6. Document the loop where an agent will read it

- [x] 6.1 Add *Driving the System End-to-End* to the root `AGENTS.md`, covering the six
      steps with real tool names, real required fields, and a success check for each.
- [x] 6.2 Lead with the prerequisites: submodule initialisation in a new worktree and how
      the failure presents (a `Literal[()]` typed-action registry and ~384 collection
      errors); the port list; how to detect a running stack older than the working tree;
      and the judge model plus `EVAL_JUDGE_<PROVIDER>_API_KEY` requirement, with
      `degraded` readiness as the symptom. Placeholder names only — no key values.
- [x] 6.3 Record the two behaviours the source does not make evident: nothing binds an
      orchestrator session to a game (the agent learns its game and seat only from the
      prompt; `session.metadata.game_id` is populated from its first game-service tool
      call), and a job stopped by the tool-round limit emits a `completion` event while
      ending `interrupted`.
- [x] 6.4 Add a *What is not a tool, and why* subsection, so an agent that cannot find a
      tool knows it was excluded and that the HTTP endpoint still works.
- [x] 6.5 Close with the check commands, why `scripts/test.sh integration` is safe against a
      live deployment (throwaway `*_test_<uuid>` database, created and dropped per run),
      and the single expected `openspec validate --all` failure,
      `spec/typed-game-actions`.
- [x] 6.6 Link the new section from the `AGENTS.md` *Useful Reading* list.
- [x] 6.7 Add the MCP endpoint column to the root `README.md` service table and an *MCP
      surfaces* section explaining the generated-tools design and the exclusion classes.
- [x] 6.8 Document each service's own surface and exclusion list in its `AGENTS.md` and
      `README.md`, for all four services — including `game-service`, whose `AGENTS.md`
      described MCP only as a working rule.
- [x] 6.9 Fix the ambiguity in `services/agent-orchestrator/AGENTS.md`, whose Tech Stack
      line described MCP as a client only; it is now both directions.
- [x] 6.10 Update `openspec/config.yaml`: the `dragncards-common` component list gains the
      MCP bootstrap, and the agent-orchestrator entry records that it is an MCP server as
      well as a client.

## 7. Verify

- [x] 7.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh`.
- [x] 7.2 `./scripts/test.sh unit` — before 1220 Python + 516 dashboard; after 1251 Python
      + 516 dashboard, all passing (shared 27→36, agent-orchestrator 418→427,
      history-service 152→159, eval-service 245→251, game-service 378 and dashboard 516
      unchanged).
- [x] 7.3 Verify the MCP transport end to end over real HTTP for one service:
      eval-service started from source on a spare port against a throwaway SQLite
      database, then `initialize` → session id, `tools/list` → exactly the six expected
      tools under their new names, `tools/call list_evaluations` → `{"requests":[]}` from
      the real handler, `tools/call stream_evaluation` → `Unknown tool`.
- [x] 7.4 Confirm the owner's running stack and the sibling agents' verification servers
      were unaffected: all four service health endpoints and ports 3020, 4102, 4114 and
      4115 still respond after the probe was stopped.
- [x] 7.5 `openspec validate --all` — only the pre-existing `spec/typed-game-actions`
      failure remains.
- [x] 7.6 Grep this change directory and the documentation it touches for `TBD`, `TODO`,
      `???`, "to be decided" and empty sections: none.

## 8. For the orchestrator, after merge

- [ ] 8.1 Rebuild and restart the app services (`./scripts/docker.sh build`, then bring
      them up), because the running stack predates this branch and will not serve `/mcp`
      on 4002, 4004 or 4005 until it does. Then confirm `GET /mcp/` returns a protocol
      rejection rather than `404` on all four ports.
- [ ] 8.2 With the four servers loaded from `.mcp.json`, drive the documented loop once
      against the live stack: create a game and load a deck, start a player agent, read its
      `tool_call` events, read the live board, request a round evaluation, read the
      verdict. This is the one thing this worktree could not do — it may not start or
      restart the shared stack — and it is what the documentation claims.
- [ ] 8.3 Set `EVAL_JUDGE_MODEL` and an `EVAL_JUDGE_<PROVIDER>_API_KEY` first, or step 8.2
      stops at the evaluation with every target `failed`. `GET :4005/ready` currently
      reports `judge_configured: false`.
- [ ] 8.4 While the stack is up, run `./scripts/test.sh integration` for
      agent-orchestrator, history-service and eval-service, which this worktree ran only as
      unit suites.
- [ ] 8.5 Delete the games and orchestrator sessions created by 8.2, so the shared stack is
      left as it was found.
