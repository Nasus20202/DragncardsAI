from __future__ import annotations

import pytest

from .cards_test_support import (
    SESSION_ID,
    UNKNOWN_ID,
    install_stub_marvel_provider,
    make_client,
    mock_manager,
    mock_session,
)


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


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
    types = {action["type"] for action in response.json()["actions"]}
    assert "load_cards" in types
    assert "unload_cards" in types
    assert "next_step" in types
    assert "draw_card" in types
    assert "move_card" in types
    assert "raw" in types


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
    op_names = {operation["op"] for operation in response.json()["raw_ops"]}
    assert "SHUFFLE_GROUP" in op_names
    assert "MOVE_CARD" in op_names
    assert "LOAD_CARDS" not in op_names


async def test_get_session_actions_raw_ops_have_required_fields():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/actions")
    for operation in response.json()["raw_ops"]:
        assert "op" in operation
        assert "description" in operation
        assert "args" in operation
        assert "returns" in operation
        assert "example" in operation
        assert isinstance(operation["example"], list)


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


async def test_openapi_session_actions_schema_lists_plugin_metadata():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["SessionActionsResponse"]
    props = schema["properties"]
    assert "plugin_metadata" in props
