"""A field this service does not define is refused, not discarded.

Pydantic's default for an undeclared key is to drop it, which means an
orchestrator predating a feature answers `200 OK` to a write it did not perform.
That is DRA-53: a current dashboard sent `session_persona` and
`allowed_subagents` to a pre-DRA-38 orchestrator, the server stored neither and
said nothing, and the user was told their subagent allowlist had been narrowed
when it had not.

The rule is asserted about the whole service rather than about the two models
that happened to be in that report — `test_every_request_body_is_strict` reads
the app's own OpenAPI document, so a request model added later that forgets
`StrictRequest` fails here instead of quietly reopening the hole.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import build_test_app


def _request_body_schema_names(openapi: dict) -> set[str]:
    """Every component schema reachable from a `requestBody`, transitively.

    Transitively, because a nested model is as much a request body as the model
    that holds it: `PlayerConfigRequest.reasoning` is where a mistyped reasoning
    key would be dropped.
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


@pytest.mark.asyncio
async def test_every_request_body_is_strict(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        openapi = app.openapi()
        names = _request_body_schema_names(openapi)
        # A guard on the guard: if the traversal stopped finding request bodies,
        # the assertion below would pass vacuously.
        assert {
            "SessionCreateRequest",
            "SessionUpdateRequest",
            "PersonaRequest",
            "PlayerConfigRequest",
            "PlayerReasoningConfig",
            "PromptRequest",
        } <= names

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
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_update_refuses_a_field_it_does_not_define(tmp_path: Path):
    """The exact shape of DRA-53, against a server that knows the fields."""
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "skew"}).json()[
                "session"
            ]["id"]

            response = client.patch(
                f"/sessions/{session_id}",
                json={"name": "renamed", "allowed_subagants": ["kawaii-girl"]},
            )

            assert response.status_code == 422
            assert "allowed_subagants" in response.text
            # Nothing is applied: a request the server cannot honour in full is
            # not honoured in part.
            after = client.get(f"/sessions/{session_id}").json()["session"]
            assert after["name"] == "skew"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_create_refuses_a_field_it_does_not_define(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions",
                json={"name": "skew", "session_personna": "kawaii-girl"},
            )

            assert response.status_code == 422
            assert "session_personna" in response.text
            assert client.get("/sessions").json()["sessions"] == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_open_mappings_still_accept_anything(tmp_path: Path):
    """Strictness is about a model's own keys.

    `metadata` is declared `dict[str, Any]`; that is its shape, not a gap in
    validation, and a caller storing arbitrary keys in it must keep working.
    """
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post(
                "/sessions",
                json={"name": "open", "metadata": {"anything": {"at": ["all"]}}},
            )

            assert response.status_code == 201
            assert response.json()["session"]["metadata"] == {
                "anything": {"at": ["all"]}
            }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registering_a_skill_without_a_name_is_still_a_400(tmp_path: Path):
    """Giving `POST /skills` a model must not move its existing error.

    A missing `name` is a check on a value, and it answered `400` before this
    change; only the body's *shape* became strict.
    """
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            assert client.post("/skills", json={}).status_code == 400
            assert client.post("/skills", json={"nmae": "x"}).status_code == 422
    finally:
        await engine.dispose()
