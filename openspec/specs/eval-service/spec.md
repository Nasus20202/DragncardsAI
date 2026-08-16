# eval-service Specification

## Purpose

The HTTP contract of eval-service — the routes, request body shapes, and response shapes that a request to evaluate one or more recorded moves goes through. The only capability this spec covers today is the validation behaviour of the request body itself; the judgement itself, the projection the judge is given, the per-round and per-game roll-ups, the round-boundary detection, the verdict write-back to history, the prompt-budget derivation, the reasoning controls, the claim epoch, the lease and heartbeat, and the idempotency are all owned by `agent-move-evaluation/spec.md`. The judge identity and the Bifrost `eval-judge` key are owned by `agent-orchestrator/spec.md` and `services/eval-service/README.md`. What stays here is the rule a request body has to follow to be accepted, and what stays in `agent-move-evaluation` is what the service does once it has accepted one.

## Requirements

### Requirement: A field the service does not define is refused, not discarded

Every request body model on `POST /games/{game_id}/evaluations` SHALL reject a key the model does not declare as a `422` response naming the key, and SHALL NOT apply any part of the request. Refusing SHALL mean the request body fails to parse, so a field that the service has never heard of is the field the caller sees named in the error — not a `200 OK` with the field silently discarded.

The check SHALL be applied at the model level (`extra="forbid"`) so the OpenAPI exporter propagates `additionalProperties: false` on every reachable request-body schema, and the same check SHALL cover models nested inside the body (`Selection`, `SeqRange`, `JudgeConfig`, `JudgeReasoning`) because a mistyped key on a nested field is as much the caller's mistake as one on the top-level body.

The check SHALL be enacted by a `StrictRequest` base class every request body inherits, and SHALL be asserted structurally by a test that reads the app's own OpenAPI document and fails if any reachable request-body schema lacks `additionalProperties: false`. A request model added later that forgets `StrictRequest` fails the test instead of quietly reopening the hole.

The check SHALL NOT apply to response models. Open-mapping fields (`metadata`, `gateway_options`, `provider_options`) keep accepting arbitrary contents; strictness is about a model's *own keys*, not the inside of a dictionary it declares as open.

The check SHALL NOT reach an MCP tool call. The path through `dragncards_common.mcp` builds the tool's input schema by flattening properties alongside path parameters and does not propagate `additionalProperties: false` to that object's root, so an unknown tool argument is dropped upstream of this rule and is a separate fix.

#### Scenario: A hallucinated key on the request body is refused

- **WHEN** a client sends `POST /games/{game_id}/evaluations` with a body that contains a key the service does not declare
- **THEN** the service SHALL respond `422` and the response SHALL name that key
- **AND** SHALL NOT create the evaluation

#### Scenario: A hallucinated key on a nested model is refused

- **WHEN** a client sends `POST /games/{game_id}/evaluations` with a `judge` block that contains a key the nested `JudgeConfig` does not declare
- **THEN** the service SHALL respond `422` and the response SHALL name that key
- **AND** SHALL NOT create the evaluation

#### Scenario: A typo in selection keys is named rather than re-explained

- **WHEN** a client sends `{"selection": {"round": [1]}}` (singular `round` instead of `rounds`)
- **THEN** the service SHALL respond `422` naming `round` as the unknown field, rather than accepting the body and surfacing the model validator's "must specify at least one of" message

#### Scenario: Every reachable request-body schema is strict

- **WHEN** the eval-service's OpenAPI document is read
- **THEN** every schema reachable from a `requestBody` (transitively, including nested models) SHALL declare that additional properties are not permitted

#### Scenario: Open mappings still accept arbitrary contents

- **WHEN** a client sends a request body that contains an open-mapping field the service declares with an arbitrary contents shape
- **THEN** the service SHALL accept the request and pass that field's contents through untouched
