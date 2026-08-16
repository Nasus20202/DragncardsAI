# Tasks

Ordered so the shared bootstrap is fixed and measured before any service test
touches it, and the docs are kept honest about the layer the flag protects.

## 1. Settle the decision and measure the baseline

- [x] 1.1 Record the choice of option 2 (`additionalProperties: false` on the
      flattened tool schema root) over option 1 (surfacing the director drop as a
      tool error) in `proposal.md`, with the limitation: the flag protects the
      inference-time layer only, and the director-time drop remains for
      non-strict clients.
- [x] 1.2 Measure the baseline in this tree: `create_session`'s root schema
      carries no `additionalProperties`, zero of 39 orchestrator tools carry it at
      the root, and the only occurrences are nested on `compact_session` and
      `save_session_player`. Recorded in `proposal.md`.

## 2. Fix the shared bootstrap

- [x] 2.1 Add the `mcp_component_fn` hook to
      `services/shared/src/dragncards_common/mcp.py`, re-applying
      `additionalProperties: false` at the root parameters object of every
      generated `OpenAPITool`, and pass it into `FastMCP.from_fastapi`.
- [x] 2.2 Add the equivalent hook to `services/game-service/src/game_service/mcp/server.py`,
      the documented exception copy that keeps an equivalent bootstrap, with a
      note that the two must stay in step.
- [x] 2.3 Update the `dragncards_common.mcp` module docstring to state that tool
      calls are strict against the endpoint's own schema, and which layer that
      protects.

## 3. Prove the flag reaches every tool

- [x] 3.1 Add a test in `services/shared/tests/test_mcp.py` asserting every tool
      the shared bootstrap builds carries `additionalProperties: false` at its
      root parameters object.
- [x] 3.2 Add a test in each of the four services' `tests/unit/test_mcp_server.py`
      asserting every reachable tool's root parameters object carries the flag,
      asserted against the real app the way the existing surface tests are
      (via `tool.parameters` server-side, and via `tool.inputSchema` where the
      game-service test lists tools through an MCP client).

## 4. Add the live refusal case

- [x] 4.1 In the agent-orchestrator's `tests/unit/test_mcp_server.py`, assert that
      validating `create_session` with `allowed_subagants: ['nope']` against the
      served input schema — the same JSON Schema validation a strict client
      applies — fails naming the key, while a valid call still validates. The
      test uses the `jsonschema` package, already present in every service venv as
      a dependency of fastmcp's `jsonschema_path`.

## 5. Keep the documentation honest

- [x] 5.1 Update `services/agent-orchestrator/AGENTS.md` ("Two MCP directions") and
      `services/agent-orchestrator/README.md` so the strictness is described as
      reaching a tool call through the flattened root, and the director-time drop
      is stated as remaining for non-strict clients.
- [x] 5.2 Confirm the `service-mcp-surface` spec delta (new requirement) says the
      same thing: inference-time refusal for a strict client, no claim about the
      director.

## 6. Validate

- [x] 6.1 `./scripts/lint.sh` clean.
- [x] 6.2 `cd services/agent-orchestrator && uv run pytest tests/unit/` green.
- [x] 6.3 `openspec validate --all` continues to report exactly one failure
      (`spec/typed-game-actions`, pre-existing on `main`); this change does NOT
      fix that.
- [x] 6.4 Archive the change with `openspec archive dra-61-mcp-strict-schemas --yes`
      and confirm the archive directory exists.
