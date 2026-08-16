"""A field this service does not define is refused, not discarded.

Pydantic's default for an undeclared key is to drop it, which means a server
predating a feature answers `200 OK` to a write it did not perform. DRA-60 is
that failure: an agent sending ``{"type": "move_card", ..., "dest_stack_indexx":
-1}`` had the typo dropped, the action executed with the default
``dest_stack_index=-1``, and the card landed at the bottom of the destination
stack instead of the top — the game went wrong silently.

The rule is asserted about the whole service rather than about the one model
that happened to be in that report — `test_every_request_body_is_strict` reads
the app's own OpenAPI document, so a request model added later that forgets
`StrictRequest` fails here instead of quietly reopening the hole.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from game_service.api.app import create_app

from .game_room_state_test_support import SESSION_ID, mock_manager, mock_session


def _request_body_schema_names(openapi: dict) -> set[str]:
    """Every component schema reachable from a `requestBody`, transitively.

    Transitively, because a nested model is as much a request body as the model
    that holds it: `LoadCardsAction.cards` is where a mistyped load key would be
    dropped, and `JudgeConfig`-style nesting in any future helper is where a
    mistyped nested key would be.
    """
    components = openapi.get("components", {}).get("schemas", {})
    seen: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    walk(components.get(name, {}))
            for key, value in node.items():
                if key != "$ref":
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for path_item in openapi.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "requestBody" in operation:
                walk(operation["requestBody"])
    return seen


def test_every_request_body_is_strict():
    app = create_app()
    openapi = app.openapi()
    names = _request_body_schema_names(openapi)
    # A guard on the guard: if the traversal stopped finding request bodies,
    # the assertion below would pass vacuously. Three of the discriminated
    # union's members and three helper-endpoint models are pinned.
    assert {
        "MoveCardAction",
        "DrawCardAction",
        "NextStepAction",
        "CreateGameRequest",
        "AttachGameRequest",
        "ResetGameRequest",
    } <= names

    # The discriminated union itself. `ActionRequest` is an `Annotated` alias
    # over `GameAction`, so FastAPI inlines it as a oneOf keyed on `type`
    # rather than emitting a component schema named "ActionRequest" — pin the
    # union structurally instead.
    actions_body = openapi["paths"]["/games/{session_id}/actions"]["post"][
        "requestBody"
    ]
    action_schema = actions_body["content"]["application/json"]["schema"]
    assert action_schema["discriminator"]["propertyName"] == "type"
    assert {
        ref["$ref"].rsplit("/", 1)[-1]
        for ref in action_schema["oneOf"]
        if "$ref" in ref
    } >= {"MoveCardAction", "DrawCardAction", "NextStepAction"}

    schemas = openapi["components"]["schemas"]
    lenient = sorted(
        name
        for name in names
        if schemas.get(name, {}).get("additionalProperties") is not False
    )
    assert lenient == [], (
        "these request-body schemas still discard unknown fields instead of "
        f"refusing them: {lenient}"
    )


def test_execute_action_refuses_a_field_it_does_not_define():
    """The DRA-60 reproduction, against a server that knows the fields."""
    session = mock_session()
    session.execute_action = AsyncMock()
    manager = mock_manager(session)
    app = create_app(session_manager=manager)
    with TestClient(app) as client:
        response = client.post(
            f"/games/{SESSION_ID}/actions",
            json={
                "type": "move_card",
                "instance_id": "x",
                "dest_group_id": "player1Hand",
                "dest_stack_indexx": -1,
            },
        )

        assert response.status_code == 422
        assert "dest_stack_indexx" in response.text
        # Nothing is executed: a request the server cannot honour in full is
        # not honoured in part.
        session.execute_action.assert_not_called()
