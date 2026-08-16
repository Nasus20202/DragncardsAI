# MCP tool calls refuse arguments the endpoint does not take

## Why

Measured during DRA-56, in this tree, with `fastmcp 3.4.5` / `pydantic 2.13.4`:
an MCP tool call silently drops an argument the endpoint does not define, and a
strict request body does not protect the call. Two findings:

1. **`extra='forbid'` does not reach a tool's input schema.** The OpenAPI
   components do gain `additionalProperties: false`, but
   `_combine_schemas_and_map_params` in `fastmcp/utilities/openapi/schemas.py`
   builds a tool's parameters by flattening the body's properties alongside the
   path parameters into a freshly constructed
   `{'type': 'object', 'properties': ..., 'required': ...}` and never copies the
   flag up to that object's root. It is preserved only on a nested model — after
   DRA-56 exactly two orchestrator tools carry one: `compact_session` at
   `properties.request.anyOf[0]` and `save_session_player` at
   `properties.reasoning.anyOf[0]`.
2. **An unknown tool argument never becomes an HTTP field at all.**
   `fastmcp/utilities/openapi/director.py:181-185` drops any argument absent from
   the route's `parameter_map` with a `WARNING` in the service's own log, which
   nothing reads. A model that hallucinates an argument gets a successful tool
   result.

Measured here before the change: `create_session`'s served input schema has no
root `additionalProperties` at all, zero of the orchestrator's 39 tools carry the
flag at the root, and the flag survives only nested on `compact_session` and
`save_session_player`.

## What Changes

### The shared MCP bootstrap sets `additionalProperties: false` on every tool schema's root

The pick is the ticket's option 2: set `additionalProperties: false` on the
flattened tool schema, which is the direction FastMCP's defaults already lean —
its own note says some clients (Claude among them) require the flag for strict
validation. The shared bootstrap (`dragncards_common.mcp`) passes FastMCP's own
`mcp_component_fn` hook into `FastMCP.from_fastapi`; the hook re-applies the flag
at the flattened root of every generated tool's parameters object. `game-service`
predates the shared library and keeps an equivalent copy of the bootstrap
(`game_service/mcp/server.py`); that copy gains the same hook, and the two are
documented as needing to stay in step.

The flag sits at the root only. A declared open mapping — session `metadata`,
`gateway_options`, `provider_options` — keeps accepting any contents, exactly as
under `extra='forbid'` on the HTTP layer: strictness is about the model's own
keys, and the root flag forbids undeclared *tool arguments*, not keys inside a
property the endpoint declares as open.

### The limitation, stated plainly

This fixes the **inference-time shape only**, not the director-time drop. A
strict client validates a generated call against the tool's input schema before
sending it, so `additionalProperties: false` at the root makes it refuse a
hallucinated argument — the call never reaches the request director that would
drop it. The server's own director still drops an argument it does not know with
a log warning, so a *non-strict* client can still provoke the old silent drop.
That is accepted: option 2 closes the hole for the clients the surface exists
for, without forking the director or waiting on an upstream fastmcp fix.

### What gets added

- The hook in `dragncards_common.mcp`, and the equivalent one in
  `game_service/mcp/server.py`.
- A test in `services/shared/tests/test_mcp.py` asserting every tool the shared
  bootstrap builds carries the flag at the root.
- A test in each service's `tests/unit/test_mcp_server.py` asserting every
  reachable tool's root parameters object carries the flag, asserted against the
  real app the way the existing surface tests are.
- A live refusal case in the agent-orchestrator's surface test: validating
  `create_session` with `allowed_subagants: ['nope']` against the served input
  schema — the same JSON Schema validation a strict client applies — fails naming
  the key, while a valid call still validates.

## Capabilities

### Modified Capabilities

- `service-mcp-surface` — a new requirement: every MCP tool's input schema
  declares at its root that additional properties are not permitted, so a strict
  client refuses a hallucinated argument at inference time instead of the request
  director dropping it and reporting success. The requirement applies to all four
  services, including `game-service`'s equivalent copy of the bootstrap.

## Impact

- **`services/shared/src/dragncards_common/mcp.py`** — the `mcp_component_fn`
  hook and its module docstring.
- **`services/game-service/src/game_service/mcp/server.py`** — the equivalent
  hook in the documented exception copy.
- **`services/shared/tests/test_mcp.py`**, and the four
  `services/*/tests/unit/test_mcp_server.py` files — the flag assertion on every
  reachable tool, plus the agent-orchestrator's live refusal case.
- **Documentation** — `services/agent-orchestrator/AGENTS.md` and
  `services/agent-orchestrator/README.md` now state that strictness reaches a
  tool call through the flattened root, and that the director-time drop remains
  for non-strict clients.
- **No HTTP-layer changes.** The flag is a property of the tool schema an MCP
  client sees; the endpoints' request validation is untouched.

## Non-goals

- **No change to the director-time drop (option 1).** Surfacing the drop as a
  tool error would require forking or patching the request director, or an
  upstream fastmcp fix. Rejected in favour of option 2, which fixes the symptom
  for the strict clients the surface exists for and needs no upstream dependency.
- **No upstream fastmcp issue filed as part of this change.** The hook is the
  supported customization point; nothing here depends on a future release.
- **No change to the HTTP request contracts.** `extra='forbid'` behaviour on the
  endpoints is unchanged and continues to be asserted by each service's
  strict-request-bodies test.
- **No change to open mappings.** `metadata`, `gateway_options` and
  `provider_options` keep accepting arbitrary contents at their own level.
