## ADDED Requirements

### Requirement: A field the service does not define is refused, not discarded

Every request body on a game-service mutation endpoint SHALL reject a key the model does not declare as a `422` response naming the key, and SHALL NOT apply any part of the request. Refusing SHALL mean the request body fails to parse, so a field that the service has never heard of is the field the caller sees named in the error — not a `200 OK` with the field silently discarded.

The check SHALL be applied at the model level (`extra="forbid"`) so the OpenAPI exporter propagates `additionalProperties: false` on every reachable request-body schema, and the same check SHALL cover every action model behind the `ActionRequest` discriminated union (`MoveCardAction`, `DrawCardAction`, `NextStepAction`, and the rest of the 25 actions in `logic/actions.py`) and every helper-endpoint request model (`CreateGameRequest`, `AttachGameRequest`, `ResetGameRequest`, `SetSeatRequest`, `SetSpectatorRequest`, `SendAlertRequest`, `SetPlayerCountRequest`). A mistyped argument to `move_card` MUST NOT execute a *different, legal* move under the dropped-argument default — that is the worse failure mode (no error surfaced, the game just goes wrong).

The check SHALL be enacted by a `StrictRequest` base class every request body inherits, and SHALL be asserted structurally by a test that reads the app's own OpenAPI document and fails if any reachable request-body schema lacks `additionalProperties: false`. A request model added later that forgets `StrictRequest` fails the test instead of quietly reopening the hole.

The check SHALL NOT apply to response models. Open-mapping fields and any field declared with an arbitrary contents shape keep accepting any keys; strictness is about a model's *own keys*, not the inside of a dictionary it declares as open.

The check SHALL NOT reach an MCP tool call. The path through `dragncards_common.mcp` builds the tool's input schema by flattening properties alongside path parameters and does not propagate `additionalProperties: false` to that object's root, so an unknown tool argument is dropped upstream of this rule and is a separate fix.

#### Scenario: A hallucinated argument on an action is refused

- **WHEN** a client sends `POST /games/{id}/actions` with `{"type": "move_card", "instance_id": "...", "dest_group_id": "player1Hand", "dest_stack_indexx": -1}` (one extra `x`)
- **THEN** the service SHALL respond `422` and the response SHALL name `dest_stack_indexx` as the unknown field
- **AND** SHALL NOT execute the move

#### Scenario: A hallucinated argument on a game-lifecycle endpoint is refused

- **WHEN** a client sends `POST /games` with a body that contains a key `CreateGameRequest` does not declare
- **THEN** the service SHALL respond `422` and the response SHALL name that key
- **AND** SHALL NOT create the game

#### Scenario: Every reachable request-body schema is strict

- **WHEN** the game-service's OpenAPI document is read
- **THEN** every schema reachable from a `requestBody` (transitively, including the action discriminated union and every action model nested behind it) SHALL declare that additional properties are not permitted

#### Scenario: Open mappings still accept arbitrary contents

- **WHEN** a client sends a request body that contains an open-mapping field the service declares with an arbitrary contents shape
- **THEN** the service SHALL accept the request and pass that field's contents through untouched
