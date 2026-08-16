# Tasks

Ordered so each section is independently shippable and a partial run leaves a green
test suite at the end of every task.

## 1. Confirm the existing pattern is the one to mirror

- [ ] 1.1 Confirm `services/agent-orchestrator/src/agent_orchestrator/schemas/base.py`
      is the single home of `StrictRequest`, and that its docstring already names
      the asymmetry, the open-mapping allowance, and the test as the structural
      guard.
- [ ] 1.2 Confirm
      `services/agent-orchestrator/tests/unit/test_app_strict_request_bodies.py`
      builds the test app, walks every `requestBody` transitively, pins a six-name
      guard list, and fails when any reachable schema lacks
      `additionalProperties: false`. The new tests mirror this exactly.
- [ ] 1.3 Confirm `services/eval-service/src/eval_service/schemas/api.py` holds all
      five request models — `EvaluationRequestBody` and the four nested
      `Selection`/`SeqRange`/`JudgeConfig`/`JudgeReasoning` — and that no other
      endpoint in the service takes a body.
- [ ] 1.4 Confirm `services/game-service/src/game_service/logic/actions.py` holds
      the 25 action models and that
      `services/game-service/src/game_service/api/models.py` holds the named
      helper-endpoint request models (`CreateGameRequest`, `AttachGameRequest`,
      `ResetGameRequest`, `SetSeatRequest`, `SetSpectatorRequest`,
      `SendAlertRequest`, `SetPlayerCountRequest`, plus any others exported by
      `api/routers/game_action_helpers.py`).
- [ ] 1.5 Confirm `services/history-service/...` `EventEnvelope` and the bundle
      records stay untouched. This change MUST NOT touch history-service.

## 2. eval-service: strict request bodies

- [ ] 2.1 Add `services/eval-service/src/eval_service/schemas/base.py` mirroring
      `services/agent-orchestrator/src/agent_orchestrator/schemas/base.py`
      byte-for-byte except for the service name in the docstring. Set
      `model_config = ConfigDict(extra="forbid")`.
- [ ] 2.2 Switch `EvaluationRequestBody`, `Selection`, `SeqRange`, `JudgeConfig`,
      and `JudgeReasoning` to inherit `StrictRequest` (which means importing it
      and changing the base class; nothing else).
- [ ] 2.3 Leave every response model on `BaseModel` (`RoundSummary`,
      `RoundListResponse`, `TargetSummary`, `EvaluationResponse`,
      `EvaluationListResponse`, `EvaluationErrorResponse` — whichever the service
      exports). Response shapes are not in this change's scope.
- [ ] 2.4 Add
      `services/eval-service/tests/unit/test_app_strict_request_bodies.py`
      mirroring the orchestrator's test: build the test app, read `app.openapi()`,
      walk request bodies transitively, pin a six-name guard list (the five from
      2.2 plus one more to make the list feel right — read the app to find an
      appropriate sixth), and fail on any schema without
      `additionalProperties: false`.
- [ ] 2.5 Add the live refusal case: a `POST /games/{game_id}/evaluations` with a
      body carrying a hallucinated key returns `422` naming that key, and the
      evaluation is not created. The exact shape of the assertion mirrors the
      orchestrator's `test_session_update_refuses_a_field_it_does_not_define`.

## 3. game-service: strict request bodies

- [ ] 3.1 Add `services/game-service/src/game_service/schemas/base.py` mirroring
      the orchestrator's `StrictRequest` base. The game-service does not yet have
      a `schemas/` directory — create it.
- [ ] 3.2 Switch every action model in
      `services/game-service/src/game_service/logic/actions.py` from `BaseModel`
      to `StrictRequest`. 25 models; one-line each. The discriminated-union
      action-endpoint model in the same file inherits `StrictRequest` too, if it
      exists.
- [ ] 3.3 Switch `CreateGameRequest`, `AttachGameRequest`, `ResetGameRequest`,
      `SetSeatRequest`, `SetSpectatorRequest`, `SendAlertRequest`,
      `SetPlayerCountRequest`, and any other request model exported by
      `api/routers/game_action_helpers.py` from `BaseModel` to `StrictRequest`
      in `services/game-service/src/game_service/api/models.py`.
- [ ] 3.4 Leave response models on `BaseModel` (`SimplifiedGameState`,
      `CreateGameResponse`, `AttachGameResponse`, `ExecuteActionResponse`,
      `ListGamesResponse`, `LookupSessionBySlugResponse`, `SessionActionsResponse`,
      `LoadPrebuiltDeckResponse`, and so on). Response shapes are not in this
      change's scope.
- [ ] 3.5 Add
      `services/game-service/tests/unit/test_app_strict_request_bodies.py`
      mirroring the orchestrator's test against the game-service app. The guard
      list pins `ActionRequest` (or whatever the discriminated-union name is),
      three of the highest-traffic action models (`MoveCardAction`,
      `DrawCardAction`, `NextStepAction`), and three helper-endpoint models
      (`CreateGameRequest`, `AttachGameRequest`, `ResetGameRequest`).
- [ ] 3.6 Add the live refusal case: a `POST /games/{id}/actions` with
      `{"type": "move_card", "instance_id": "...", "dest_group_id": "player1Hand",
      "dest_stack_indexx": -1}` (one extra `x`) returns `422` naming
      `dest_stack_indexx`, and the action is not executed.

## 4. Validation, lint, unit tests

- [ ] 4.1 `./scripts/lint.sh` clean across the three Python services.
- [ ] 4.2 `./scripts/test.sh unit` green — eval-service 38+ tests, game-service
      50+ tests, plus the two new test files each green.
- [ ] 4.3 `openspec validate --all` continues to report exactly one failure
      (`spec/typed-game-actions`, pre-existing on `main`); this change does NOT
      fix that.
