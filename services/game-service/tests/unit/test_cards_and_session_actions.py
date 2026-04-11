"""
Unit tests for GET /cards and GET /games/{id}/actions endpoints.

Uses httpx.AsyncClient with ASGITransport + mocked SessionManager.
Card DB is tested directly via the card_db module (no mocking needed —
it reads real fixture files from the repo).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from game_service.api.app import create_app
from game_service.session.card_db import search_cards
from game_service.session.manager import SessionNotFoundError

SESSION_ID = "test-session-id"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session(plugin_name: str = "marvel-champions") -> MagicMock:
    session = MagicMock()
    session.session_id = SESSION_ID
    session.plugin_name = plugin_name
    return session


def _mock_manager(session=None) -> MagicMock:
    manager = MagicMock()
    _session = session or _mock_session()

    async def get_session(sid):
        if sid == SESSION_ID:
            return _session
        raise SessionNotFoundError(f"Session {sid!r} not found")

    manager.get_session = get_session
    manager.list_sessions = MagicMock(return_value=[])
    return manager


def _make_client(manager=None):
    app = create_app(session_manager=manager or _mock_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


# ---------------------------------------------------------------------------
# card_db.search_cards unit tests (no HTTP — pure logic)
# ---------------------------------------------------------------------------


def test_search_cards_by_name_returns_results():
    results = search_cards(name="Spider-Man", type_code="hero")
    assert len(results) > 0
    for r in results:
        assert "spider-man" in r["name"].lower()
        assert r["type_code"] == "hero"


def test_search_cards_returns_database_id():
    results = search_cards(name="Black Panther", type_code="hero")
    assert len(results) > 0
    for r in results:
        assert len(r["database_id"]) == 36  # UUID format
        assert r["database_id"].count("-") == 4


def test_search_cards_type_filter():
    results = search_cards(name="Spider-Man", type_code="villain")
    # No hero named Spider-Man should be a villain
    for r in results:
        assert r["type_code"] == "villain"


def test_search_cards_classification_filter():
    results = search_cards(type_code="ally", classification="Justice", limit=5)
    for r in results:
        assert r["type_code"] == "ally"
        assert "justice" in (r["classification"] or "").lower()


def test_search_cards_limit_respected():
    results = search_cards(type_code="ally", limit=3)
    assert len(results) <= 3


def test_search_cards_deduplicates_by_database_id():
    results = search_cards(name="Iron Man")
    db_ids = [r["database_id"] for r in results]
    assert len(db_ids) == len(set(db_ids)), "No duplicate databaseIds in results"


def test_search_cards_official_only_default():
    results = search_cards(name="Spider-Man", type_code="hero")
    for r in results:
        assert r["official"] is True


def test_search_cards_empty_query_returns_up_to_limit():
    results = search_cards(limit=10)
    assert len(results) <= 10


# ---------------------------------------------------------------------------
# GET /cards HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_get_cards_200():
    async with _make_client() as client:
        resp = await client.get(
            "/cards", params={"name": "Spider-Man", "type_code": "hero"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "cards" in data
    assert "total" in data
    assert data["total"] == len(data["cards"])
    assert data["total"] > 0


async def test_get_cards_each_has_database_id():
    async with _make_client() as client:
        resp = await client.get("/cards", params={"name": "Black Panther"})
    assert resp.status_code == 200
    for card in resp.json()["cards"]:
        assert "database_id" in card
        assert len(card["database_id"]) == 36


async def test_get_cards_type_filter():
    async with _make_client() as client:
        resp = await client.get(
            "/cards", params={"name": "Nick Fury", "type_code": "ally"}
        )
    assert resp.status_code == 200
    data = resp.json()
    for card in data["cards"]:
        assert card["type_code"] == "ally"


async def test_get_cards_limit_param():
    async with _make_client() as client:
        resp = await client.get("/cards", params={"type_code": "ally", "limit": 5})
    assert resp.status_code == 200
    assert resp.json()["total"] <= 5


async def test_get_cards_no_params_returns_200():
    async with _make_client() as client:
        resp = await client.get("/cards")
    assert resp.status_code == 200


async def test_get_cards_limit_over_200_rejected():
    async with _make_client() as client:
        resp = await client.get("/cards", params={"limit": 201})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /games/{session_id}/actions HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_get_session_actions_200():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == SESSION_ID
    assert data["plugin_name"] == "marvel-champions"
    assert isinstance(data["actions"], list)
    assert isinstance(data["load_groups"], list)
    assert isinstance(data["raw_ops"], list)


async def test_get_session_actions_includes_all_types():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    types = {a["type"] for a in resp.json()["actions"]}
    assert "load_cards" in types
    assert "unload_cards" in types
    assert "next_step" in types
    assert "draw_card" in types
    assert "move_card" in types
    assert "raw" in types


async def test_get_session_actions_each_has_schema():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    for action in resp.json()["actions"]:
        assert "type" in action
        assert "description" in action
        assert "schema" in action


async def test_get_session_actions_raw_ops_present():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    ops = resp.json()["raw_ops"]
    op_names = {o["op"] for o in ops}
    assert "SHUFFLE_GROUP" in op_names
    assert "MOVE_CARD" in op_names
    assert "LOAD_CARDS" not in op_names  # load_cards is a typed action, not a raw op


async def test_get_session_actions_raw_ops_have_required_fields():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    for op in resp.json()["raw_ops"]:
        assert "op" in op
        assert "description" in op
        assert "args" in op
        assert "returns" in op
        assert "example" in op
        assert isinstance(op["example"], list)


async def test_get_session_actions_load_groups_for_marvel():
    async with _make_client() as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    groups = resp.json()["load_groups"]
    assert "playerNDeck" in groups
    assert "sharedEncounterDeck" in groups
    assert "sharedVillain" in groups


async def test_get_session_actions_404():
    async with _make_client() as client:
        resp = await client.get(f"/games/{UNKNOWN_ID}/actions")
    assert resp.status_code == 404


async def test_get_session_actions_unknown_plugin_returns_empty_groups():
    session = _mock_session(plugin_name="unknown-plugin")
    manager = _mock_manager(session=session)
    async with _make_client(manager=manager) as client:
        resp = await client.get(f"/games/{SESSION_ID}/actions")
    assert resp.status_code == 200
    assert resp.json()["load_groups"] == []


# ---------------------------------------------------------------------------
# GET /actions (global) HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_get_global_actions_200():
    async with _make_client() as client:
        resp = await client.get("/actions")
    assert resp.status_code == 200
    data = resp.json()
    assert "actions" in data
    assert "raw_ops" in data


async def test_get_global_actions_typed_actions():
    async with _make_client() as client:
        resp = await client.get("/actions")
    types = {a["type"] for a in resp.json()["actions"]}
    assert "next_step" in types
    assert "load_cards" in types
    assert "raw" in types


async def test_get_global_actions_raw_ops_curated():
    async with _make_client() as client:
        resp = await client.get("/actions")
    ops = resp.json()["raw_ops"]
    assert len(ops) > 10  # curated, not empty
    op_names = {o["op"] for o in ops}
    assert "SHUFFLE_GROUP" in op_names
    assert "MOVE_STACK" in op_names
    assert "LOOK_AT" in op_names
    assert "FILTER_CARDS" in op_names
    assert "DEFINE" in op_names


async def test_get_global_actions_each_raw_op_has_example():
    async with _make_client() as client:
        resp = await client.get("/actions")
    for op in resp.json()["raw_ops"]:
        assert isinstance(op["example"], list), f"{op['op']} has no example"
        assert len(op["example"]) >= 1
