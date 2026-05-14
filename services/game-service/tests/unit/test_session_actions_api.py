"""
Unit tests for session action catalogs and HTTP action endpoints.
"""

from __future__ import annotations

from game_service.logic.action_catalog import build_action_catalog_entries

from ._api_test_helpers import (
    SESSION_ID,
    UNKNOWN_ID,
    make_client,
    mock_manager,
    mock_session,
)

# ---------------------------------------------------------------------------
# GET /games/{session_id}/actions HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_get_session_actions_200():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == SESSION_ID
    assert data["plugin_name"] == "marvel-champions"
    assert isinstance(data["actions"], list)
    assert isinstance(data["load_groups"], list)
    assert isinstance(data["raw_ops"], list)
    assert isinstance(data["plugin_metadata"], dict)


async def test_get_session_actions_includes_all_types():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    action_types = {action["type"] for action in response.json()["actions"]}
    assert {
        "load_cards",
        "unload_cards",
        "next_step",
        "draw_card",
        "move_card",
        "raw",
    }.issubset(action_types)


async def test_get_session_actions_each_has_schema():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    for action in response.json()["actions"]:
        assert "type" in action
        assert "description" in action
        assert "schema" in action


async def test_get_session_actions_raw_ops_present():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    op_names = {op["op"] for op in response.json()["raw_ops"]}
    assert "SHUFFLE_GROUP" in op_names
    assert "MOVE_CARD" in op_names
    assert "LOAD_CARDS" not in op_names


async def test_get_session_actions_raw_ops_have_required_fields():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    for op in response.json()["raw_ops"]:
        assert "op" in op
        assert "description" in op
        assert "args" in op
        assert "returns" in op
        assert "example" in op
        assert isinstance(op["example"], list)


async def test_get_session_actions_load_groups_for_marvel():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    groups = response.json()["load_groups"]
    assert "playerNDeck" in groups
    assert "sharedEncounterDeck" in groups
    assert "sharedVillain" in groups
    assert "sharedVillainDiscard" in groups
    assert "playerNOutOfPlay" in groups


async def test_get_session_actions_plugin_metadata_for_marvel():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    metadata = response.json()["plugin_metadata"]
    assert any(item["id"] == "toggleExhaust" for item in metadata["named_action_lists"])
    assert any(
        item["scope"] == "game" and item["key"] == "D" for item in metadata["hotkeys"]
    )
    assert any(item["id"] == "drawCard" for item in metadata["touch_bar"])
    assert any(
        item["layout_id"] == "standard2Player"
        for item in metadata["player_count_layouts"]
    )
    assert "playerNDeck" in metadata["load_groups"]


async def test_get_session_actions_404():
    async with make_client() as client:
        response = await client.get(f"/games/{UNKNOWN_ID}/actions")
    assert response.status_code == 404


async def test_get_session_actions_unknown_plugin_returns_empty_groups():
    session = mock_session(plugin_name="unknown-plugin")
    manager = mock_manager(session=session)
    async with make_client(manager=manager) as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    assert response.status_code == 200
    assert response.json()["load_groups"] == []
    assert response.json()["plugin_metadata"] == {
        "named_action_lists": [],
        "hotkeys": [],
        "touch_bar": [],
        "default_actions": [],
        "player_count_layouts": [],
        "load_groups": [],
    }


# ---------------------------------------------------------------------------
# GET /actions (global) HTTP endpoint tests
# ---------------------------------------------------------------------------


async def test_get_global_actions_200():
    async with make_client() as client:
        response = await client.get("/actions")
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data
    assert "raw_ops" in data
    assert "plugin_metadata" not in data


async def test_get_global_actions_typed_actions():
    async with make_client() as client:
        response = await client.get("/actions")
    action_types = {action["type"] for action in response.json()["actions"]}
    assert "next_step" in action_types
    assert "load_cards" in action_types
    assert "raw" in action_types


def test_shared_action_catalog_matches_http_types():
    entries = build_action_catalog_entries()
    action_types = {entry["type"] for entry in entries}
    assert "next_step" in action_types
    assert "set_player_count" in action_types
    assert "load_cards" in action_types


async def test_get_global_actions_raw_ops_curated():
    async with make_client() as client:
        response = await client.get("/actions")
    raw_ops = response.json()["raw_ops"]
    assert len(raw_ops) > 10
    op_names = {op["op"] for op in raw_ops}
    assert "SHUFFLE_GROUP" in op_names
    assert "MOVE_STACK" in op_names
    assert "LOOK_AT" in op_names
    assert "FILTER_CARDS" in op_names
    assert "DEFINE" in op_names


async def test_get_global_actions_each_raw_op_has_example():
    async with make_client() as client:
        response = await client.get("/actions")
    for op in response.json()["raw_ops"]:
        assert isinstance(op["example"], list), f"{op['op']} has no example"
        assert len(op["example"]) >= 1


async def test_openapi_session_actions_schema_lists_plugin_metadata():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["SessionActionsResponse"]
    assert "plugin_metadata" in schema["properties"]
