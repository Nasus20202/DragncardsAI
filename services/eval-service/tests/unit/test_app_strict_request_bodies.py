"""A field this service does not define is refused, not discarded.

Pydantic's default for an undeclared key is to drop it, which means a server
predating a feature answers `200 OK` to a write it did not perform. DRA-60 is
that failure: a client sending ``{"selection": {"round": [1]}}`` — ``round``
where the model declares ``rounds`` — had the unknown key dropped, and the
server's own "selection must specify at least one of..." error never named the
typo.

The rule is asserted about the whole service rather than about the one model
that happened to be in that report — `test_every_request_body_is_strict` reads
the app's own OpenAPI document, so a request model added later that forgets
`StrictRequest` fails here instead of quietly reopening the hole.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from eval_service.config import Settings
from eval_service.runtime.app import create_app
from eval_service.schema_migrations import ensure_schema
from eval_service.storage.db import create_session_factory
from eval_service.storage.repository import Repository
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)


def _request_body_schema_names(openapi: dict) -> set[str]:
    """Every component schema reachable from a `requestBody`, transitively.

    Transitively, because a nested model is as much a request body as the model
    that holds it: `EvaluationRequestBody.selection` is where a mistyped
    selection key would be dropped, and `JudgeConfig.reasoning` is where a
    mistyped reasoning key would be.
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
    app = create_app(start_worker=False)
    openapi = app.openapi()
    names = _request_body_schema_names(openapi)
    # A guard on the guard: if the traversal stopped finding request bodies,
    # the assertion below would pass vacuously. eval-service's whole request
    # body surface is these five models, so every one of them is pinned — and
    # the sixth pin is the negative: `RoundSummary` is reachable only through
    # the *response* path (inside `RoundListResponse`), so its absence here
    # proves the traversal walks request bodies and not everything in sight.
    assert {
        "EvaluationRequestBody",
        "Selection",
        "SeqRange",
        "JudgeConfig",
        "JudgeReasoning",
    } <= names
    assert "RoundSummary" not in names

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


@pytest.mark.asyncio
async def test_create_evaluation_refuses_a_field_it_does_not_define():
    """The DRA-60 reproduction, against a server that knows the fields."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        settings = Settings(eval_judge_model="anthropic/claude-x")
        history = FakeHistoryClient(
            {
                "g1": [
                    state_event(game_id="g1", seq=1, round_number=1),
                    agent_event(game_id="g1", seq=2),
                ]
            }
        )
        judge = StubJudgeClient()
        app = create_app(
            settings=settings,
            repository=repo,
            history_client=history,
            judge_client=judge,
            start_worker=False,
        )
        with TestClient(app) as client:
            response = client.post(
                "/games/g1/evaluations",
                json={
                    "scope": "round",
                    "selection": {"rounds": [1], "round": [1]},
                },
            )

            assert response.status_code == 422
            assert '"round"' in response.text
            # Nothing is created: a request the server cannot honour in
            # full is not honoured in part.
            assert client.get("/evaluations").json()["requests"] == []
    finally:
        await engine.dispose()
