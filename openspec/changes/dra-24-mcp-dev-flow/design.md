# Design notes (DRA-24)

## Generate the tools, do not write them

`FastMCP.from_fastapi` reads the FastAPI app a service already builds and turns each route
into a tool with the route's own request and response models as its schema. The alternative
— a hand-written tool module per service — was rejected for one reason: it is a second
implementation of the API, and the two drift. `services/game-service/AGENTS.md` already
carries the rule "MCP tools must match HTTP endpoint functionality", and a generated
surface is the only version of that rule that does not depend on a reviewer noticing.

The cost is that a tool's *name* is no longer a free choice: it is the endpoint's
`operation_id`. That is why the 65 explicit `operation_id` values are part of this change
rather than a follow-up. Without them FastAPI generates
`submit_prompt_sessions__session_id__prompts_post`, and FastMCP shortens that to a lossy
`restore_game_games`-style name. Truncation is both unreadable and collision-prone, so the
naming had to be fixed in the same change that made the names load-bearing.

The knock-on rule, written into every service's `AGENTS.md`: **adding a route now adds an
MCP tool automatically, so a new route must carry an explicit `operation_id`.**

## Where the mount goes, and why not the app factory

`mount_mcp_server` is called from each service's `main.py` on the app the factory returned,
not inside the factory. Two reasons:

- The test suites call `create_app` directly, many times per run. Building a FastMCP server
  from the OpenAPI schema on every one of those, and starting an MCP session manager that
  no test uses, is pure cost.
- `game-service` already does it this way, so there was an established shape to match.

The MCP transport has its own lifespan and does nothing unless it is started, so the app's
existing `lifespan_context` is wrapped with `combine_lifespans` rather than replaced.
Replacing it would silently skip the service's own startup — its database engine, its
migrations, its worker — which is the kind of failure that shows up as an unrelated
connection error much later.

Because the mount lives in the entrypoint, the test that proves it is wired asserts on the
entrypoint: each service's `test_telemetry.py` ordering assertion now expects
`["setup_telemetry", "create_app", "mount_mcp", "run"]`, and `test_mcp_server.py` asserts
`main.mount_mcp is mcp_server.mount`. Without the first of those, removing the mount from
`main.py` would break nothing that runs.

## The exclusion list is the security surface

None of these services authenticates a caller. They listen on localhost and, in Compose, on
the internal network. So an MCP surface is not merely a convenience layer: every tool left
in it is an operation a model can perform on a running deployment with no further check,
and on a shared local stack that deployment belongs to someone else.

`game-service` set the precedent this change follows — it excludes its snapshot
import/export, room-control and raw-DragnLang routes from MCP while keeping them on HTTP.
The generalisation, with the reasoning attached, now lives in the `dragncards_common.mcp`
module docstring so it is read by whoever adds the next service. Three classes:

**Probes.** `/health` and `/ready`, for every service, non-overridably. They tell an LLM
nothing and crowd the tool list. A caller cannot opt back in; a test asserts that.

**Anything whose response does not end.** An MCP tool call reads its response to
completion, so mapping a server-sent-event route to a tool hangs the caller until it times
out — `stream_job_events`, `stream_evaluation`. `export_game_bundle` is the same class for a
different reason: it completes, but only by handing back an entire recorded game as NDJSON,
which is a context window spent on data the paged read next to it returns properly. In every
case there is a paged read alongside, and the documentation names it.

**Irreversible destruction and deployment-global mutation.** `delete_game_history` drops the
only durable record of what an agent did — the evidence a debugging loop exists to read.
`backfill_game_event` and `import_game_bundle` write into the ordered store, and a
fabricated event corrupts the record while every read still looks healthy.
`clear_evaluations` is an unscoped bulk delete of terminal requests across the deployment,
not just the caller's. The skill registry, MCP registry and persona table are
deployment-global: an entry changed there changes what every session resolves, including a
session someone else is running. Reads of all of these stay exposed.

The line was drawn at blast radius, not at read-versus-write. Per-session and per-object
writes stay exposed precisely so an agent can clean up after itself — `delete_game`,
`terminate_session`, `delete_session`, `disable_session_skill`, `remove_session_mcp`,
`delete_evaluation`. Removing those would have produced a surface that can only create, on a
shared stack, which is worse.

Method-level exclusion exists because of one concrete case: history-service's
`/games/{game_id}/events` is a safe paged read on `GET` and a write into the ordered store
on `POST`. A path-only exclusion would have cost the transcript read that step 3 of the loop
depends on, so `ExcludedRoute` accepts `(pattern, methods)` as well as a bare pattern.

## Why the tests assert against the real app

The exclusions are regexes matched against generated OpenAPI paths, and **a pattern that
matches nothing looks exactly like a pattern that works** — the tool is absent either way
only if you are lucky. So each service's `test_mcp_server.py` builds that service's real
FastAPI app, mounts the real surface, and asserts on the resulting tool names: the tools the
loop needs are present, the excluded ones are absent. Asserting on the contents of
`EXCLUDED_ROUTES` would have passed for a typo'd pattern.

## Documentation placement

The flow went into the root `AGENTS.md` rather than a new file. That file is what every
assistant setup on this project reads first, and a separate document is one an agent has to
already know exists. `README.md` gets the MCP endpoint table and the *why* of the design;
each service's own `AGENTS.md` and `README.md` get its specific exclusion list, since that
is the thing someone changing that service needs.

The prerequisites lead the section rather than trailing it. All four are failures that
happen before any code is exercised, and each one presents as something else: an empty
submodule presents as 384 unrelated collection errors, a stale container presents as a
missing endpoint, an unconfigured judge presents as every evaluation target failing, and the
known `openspec` failure presents as a validation problem the agent just caused. A
prerequisite discovered after the fact has already cost the time it existed to save.
