# eval-service and game-service: refuse request-body fields the service does not define

## Why

DRA-56 made every agent-orchestrator request body reject a field it does not define (`extra="forbid"`). The other two services still have Pydantic's default for an undeclared key, which is to drop it, so a mistyped or version-skewed field is accepted and silently ignored. Pydantic's `extra="forbid"` is the switch, and the pattern from the orchestrator is already load-bearing — `tests/unit/test_app_strict_request_bodies.py` reads the app's own OpenAPI document and fails if any request body is missing it.

The eval-service half is small and clearly worth doing. The one body in the service, `EvaluationRequestBody`, and the four nested models (`Selection`, `SeqRange`, `JudgeConfig`, `JudgeReasoning`) are the whole surface. Concretely bad today: `{"selection": {"round": [1]}}` (singular) silently becomes an empty selection and trips the model validator's "must specify at least one of" message, instead of naming `round` as the unknown key.

The game-service half is larger. Twenty-five action models behind the `ActionRequest` discriminated union in `logic/actions.py:455-480`, each of which is *also* a request body on its own helper endpoint in `api/routers/game_action_helpers.py`, plus `CreateGameRequest`, `AttachGameRequest`, `ResetGameRequest`, `SetSeatRequest`, `SetSpectatorRequest`, `SendAlertRequest`, `SetPlayerCountRequest`. **Worse than the orchestrator's failure mode**: a mistyped argument to `move_card` does not fail — it executes a *different, legal* move. The game just goes wrong.

Two surfaces are correctly lenient and MUST NOT be tightened:

- `services/history-service/src/history_service/schemas/envelope.py:69` — `EventEnvelope` is `ConfigDict(extra="allow")` and the `history-event-store` spec requires forward-compatibility for unknown fields.
- `services/history-service/src/history_service/schemas/transfer.py` — five bundle records at `extra="ignore"`, documented in the file as forward-compatibility for a bundle written by a newer service.

Tightening either would break a stated requirement. This change does not touch `history-service`.

## What Changes

- **`extra="forbid"`** on every request body model in eval-service and game-service. Response models and open mappings stay open.
- A **`StrictRequest` base** per service, mirroring `services/agent-orchestrator/src/agent_orchestrator/schemas/base.py`. The docstring on each states the asymmetry, the open-mapping allowance, and that the test is the structural guard.
- **A structural test per service**, mirroring `tests/unit/test_app_strict_request_bodies.py`. It reads the app's own OpenAPI document, walks every request-body schema transitively, and fails if any schema lacks `additionalProperties: false`. A new model added later that forgets `StrictRequest` fails the test instead of quietly reopening the hole.

### Modified Capabilities

- `agent-move-evaluation` — every request body on `POST /games/{game_id}/evaluations` and the four nested models refuses a field it does not define; the read endpoints are untouched.
- `game-service` — every request body on the action endpoints, the game-lifecycle endpoints, and the prebuilt-deck load endpoint refuses a field it does not define; every read endpoint is untouched.

### Impact

- **agent-orchestrator** — none. The orchestrator already carries this (DRA-56).
- **dashboard** — none directly. The dashboard's `unappliedSessionSettings()` already detects a dropped setting *after the fact*; that stays.
- **eval-service** — `services/eval-service/src/eval_service/schemas/api.py` (each request body inherits `StrictRequest`); a new `services/eval-service/src/eval_service/schemas/base.py`; a new `services/eval-service/tests/unit/test_app_strict_request_bodies.py` mirroring the orchestrator's test.
- **game-service** — `services/game-service/src/game_service/api/models.py` (each request body inherits `StrictRequest`); `services/game-service/src/game_service/logic/actions.py` (each of the 25 action models does the same); a new `services/game-service/src/game_service/schemas/base.py`; a new `services/game-service/tests/unit/test_app_strict_request_bodies.py` mirroring the orchestrator's test.
- **history-service** — none. Its `EventEnvelope` and bundle records are documented forward-compatibility, which `extra="forbid"` would break.
- **Documentation** — none required; the pattern is already documented at the shared call site in `services/agent-orchestrator/src/agent_orchestrator/schemas/base.py`, which both new files reference.

## Non-goals

- **No loosening to make a caller pass.** A refused field is the entire point of the check.
- **No response-model changes.** The check is asymmetrically about a model's own keys. `metadata`, `gateway_options`, and `provider_options` keep accepting anything; their parent models stay as they are.
- **No MCP-surface fix.** DRA-61 covers the FastMCP-specific problem that an unknown tool argument drops silently rather than refusing (an effect of `fastmcp/utilities/openapi/director.py:181-185`), and a separate path through the shared bootstrap. This change covers the HTTP layer only.
- **No capability endpoint.** DRA-59 covers a separate `/capabilities` endpoint so a client can detect server version skew before sending anything; that is complementary, not an alternative.
- **No history-service changes.** Both already-tolerant surfaces are deliberate forward-compatibility.
- **No per-field tightening beyond `extra="forbid"`.** The whole point is to make a refused field name the wrong key, not to change any existing validation of values the model knows.
