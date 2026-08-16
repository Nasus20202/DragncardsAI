# Design: two services inherit the orchestrator's strict-request pattern

## The pattern, in one paragraph

`extra="forbid"` on every request body, asserted structurally against the app's own OpenAPI document. `tests/unit/test_app_strict_request_bodies.py` walks every `requestBody` schema transitively (nested models are as much a request body as the model that holds them — `PlayerConfigRequest.reasoning` is where a mistyped reasoning key would be dropped) and fails if any lacks `additionalProperties: false`. The base class is easy to forget; the test is the part that matters.

## Why a base class per service instead of sharing through `dragncards_common`

`dragncards_common` already holds shared Python helpers (`telemetry`, `mcp`, `bifrost`, `resp_connection`, `schema_migrations`). Each service owns its own `schemas/` directory today — `services/agent-orchestrator/src/agent_orchestrator/schemas/`, `services/eval-service/src/eval_service/schemas/`, `services/game-service/src/game_service/...` does not yet have one but will, mirroring the orchestrator's layout. A shared `StrictRequest` in `dragncards_common` would be a small, real, reusable import — but adding a Python module to the shared package for a six-line class is the kind of "infrastructure-first" change that ages badly when two of the four services don't need it and a fifth one day will. The orchestrator's own `StrictRequest` is the file we mirror, and the two new copies are pinned in their service's test the same way. Hoisting this is a future change's call.

## Why the strictness reaches a request body, and what it does NOT reach

Pydantic's `model_config = ConfigDict(extra="forbid")` is applied at the **model** level. The OpenAPI exporter propagates `additionalProperties: false` to any schema generated from that model. So the check fires on a body the router sees — but only on a body that has been *parsed* by Pydantic. The check does **not** reach:

- **FastMCP tool arguments.** The path through `dragncards_common.mcp` builds the tool's input schema by flattening the body's properties alongside path parameters into a fresh object (per the source on
  `fastmcp/utilities/openapi/schemas.py`) and does not propagate `additionalProperties: false` to that object's root. So a model that hallucinates an argument never reaches the request body, and the silent drop happens upstream of the rule. **That is DRA-61's scope, not this change's.**
- **An unmodelled body.** A route whose handler takes `dict[str, Any]` is a hole the rule cannot reach; `POST /skills` was the last one in the orchestrator. The action helper endpoints in game-service are typed against the `ActionRequest` discriminated union, not `dict`, so this is not an issue in either of the two services this change touches.
- **An open mapping inside a model.** `metadata`, `gateway_options`, and `provider_options` keep accepting arbitrary contents — strictness is about a model's *own keys*, not the inside of a dictionary the model declares as open. Open mappings are excluded by looking only at the schema's top-level `additionalProperties`, which `false` would set; the open-dict field's own (open) sub-schema is not in scope.

## The shape of the test, mirrored exactly

`tests/unit/test_app_strict_request_bodies.py` already exists in the orchestrator:

1. Build the test app.
2. Read `app.openapi()`.
3. Walk every `requestBody` schema transitively (paths → operations → `requestBody` → `$ref` chain).
4. Assert the set of reachable schema names covers a guard list (the orchestrator pins `SessionCreateRequest`, `SessionUpdateRequest`, `PersonaRequest`, `PlayerConfigRequest`, `PlayerReasoningConfig`, `PromptRequest`) — a guard on the guard, so a stopped traversal would not silently pass.
5. Compute `lenient = [n for n in names if schemas[n].get("additionalProperties") is not False]`.
6. Fail with `f"these request-body schemas still discard unknown fields: {lenient}"` if non-empty.

Each service's test file does the same and pins its own six names — the eval-service guard list is `[EvaluationRequestBody, Selection, SeqRange, JudgeConfig, JudgeReasoning, RoundSummary]` (where `RoundSummary` is intentionally *excluded*; `RoundListResponse` is the response shape, not the body — the test will assert it appears as reachable through the response path but the test never reads responses, so this is just bookkeeping). The game-service guard list is `[ActionRequest, MoveCardAction, DrawCardAction, CreateGameRequest, AttachGameRequest, ResetGameRequest]` — the discriminated union plus three high-traffic models.

The test also asserts that a known call (the orchestrator's `test_session_update_refuses_a_field_it_does_not_define` against `{"name": "renamed", "allowed_subagants": ["kawaii-girl"]}`) still produces a `422` naming the field and does not apply any part of the request. Each new service's test takes the same shape against a representative endpoint — eval-service's `POST /games/{game_id}/evaluations` with a real-shape body carrying a hallucinated key, game-service's `POST /games/{id}/actions` with `{"type": "move_card", "instance_id": "...", "dest_group_id": "player1Hand", "dest_stack_indexx": -1}` (one extra `x`).

## The order: eval-service first, then game-service

Eval-service has one body and four nested models. Land it first to:

1. Confirm the mirrored test passes against a real service.
2. Establish the per-service test file's shape before the larger sweep.

Game-service then runs the same fix on 25 action models and 8 helper endpoint models. The discriminated union means most of the action models share one router, so the per-service test's guard list stays short.

## Alternatives rejected

- **Loosening `extra="forbid"` to `extra="ignore"` to stop breaking callers.** That is the orchestrator's pre-DRA-56 default and is exactly the bug. A field this service does not implement is, by definition, a caller sending something this service does not implement.
- **OpenMapping per-service helper, more permissive than `extra="forbid"`.** The asymmetry already exists at the field level (a `metadata` field stays open). A second base class for "models with a metadata-like field" is an abstraction in search of one caller — the orchestrator does not have one, and neither service this change touches has one outside what already exists.
- **A shared base class in `dragncards_common`.** See above. Two copies; not yet earned.
- **A dict-only schema-diff test that loads every module and imports every symbol.** It would catch the same bug and break equally on indirect types. Reading OpenAPI is what the orchestrator's pattern does and what the existing test does; the new copies mirror it.

## Concrete reproduction, both halves

Eval-service against `{"selection": {"round": [1]}}`:
- **Today** — the request is accepted with `200 OK`-equivalent behaviour, `selection` arrives empty, and the model validator raises `"selection must specify at least one of: seqs, rounds, seq_range, whole_game"`. The caller does not learn that `round` was the typo.
- **After this change** — the body fails to parse with `422` and the response names `round` as the unknown field.

Game-service against `{"type": "move_card", "instance_id": "x", "dest_group_id": "y", "dest_stack_indexx": -1}`:
- **Today** — Pydantic ignores `dest_stack_indexx`, the action executes with the default `dest_stack_index=-1`, and the card lands at the bottom of the destination stack instead of the top. The game just goes wrong silently.
- **After this change** — the body fails to parse with `422` and the response names `dest_stack_indexx`.

Both are real, both are reproducible, and both share the fix.
