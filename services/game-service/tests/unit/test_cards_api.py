from __future__ import annotations

import pytest

from game_service.logic.action_catalog import build_action_catalog_entries

from .cards_test_support import install_stub_marvel_provider, make_client


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


async def test_list_card_providers_200():
    async with make_client() as client:
        response = await client.get("/card-providers")

    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    provider = next(
        item for item in body["providers"] if item["provider"] == "marvel-champions"
    )
    assert provider["default"] is True
    assert "load_groups" in provider
    assert "filters" in provider


async def test_search_provider_cards_200():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions",
            params={"name": "Spider-Man", "type_code": "hero"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "cards" in data
    assert "total" in data
    assert data["total"] == len(data["cards"])
    assert data["total"] > 0


async def test_search_provider_cards_each_has_database_id():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions", params={"name": "Black Panther"}
        )
    assert response.status_code == 200
    for card in response.json()["cards"]:
        assert "database_id" in card
        assert len(card["database_id"]) == 36


async def test_search_provider_cards_exposes_expanded_fields():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions", params={"name": "Black Panther"}
        )
    assert response.status_code == 200
    card = response.json()["cards"][0]
    assert "attributes" in card
    assert "artificial_id" in card["attributes"]
    assert "id" in card["attributes"]
    assert "type" in card["attributes"]
    assert "rules" in card["attributes"]
    assert "unique" in card["attributes"]


async def test_search_provider_cards_type_filter():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions", params={"name": "Nick Fury", "type_code": "ally"}
        )
    assert response.status_code == 200
    for card in response.json()["cards"]:
        assert card["type_code"] == "ally"


async def test_search_provider_cards_limit_param():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions", params={"type_code": "ally", "limit": 5}
        )
    assert response.status_code == 200
    assert response.json()["total"] <= 5


async def test_search_provider_cards_no_params_returns_200():
    async with make_client() as client:
        response = await client.get("/cards/marvel-champions")
    assert response.status_code == 200


async def test_search_provider_cards_unknown_filter_rejected():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions", params={"unknown": "value"}
        )
    assert response.status_code == 400
    assert "Unsupported filter" in response.json()["detail"]


async def test_search_provider_cards_limit_over_200_rejected():
    async with make_client() as client:
        response = await client.get("/cards/marvel-champions", params={"limit": 201})
    assert response.status_code == 422


async def test_search_provider_cards_supports_explicit_false_boolean_filter():
    async with make_client() as client:
        response = await client.get(
            "/cards/marvel-champions",
            params={
                "name": "Spider-Man",
                "type_code": "hero",
                "official_only": "false",
            },
        )

    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_cards_openapi_lists_provider_specific_filters():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    operation = response.json()["paths"]["/cards/marvel-champions"]["get"]
    param_names = {param["name"] for param in operation["parameters"]}
    assert param_names == {
        "name",
        "type_code",
        "classification",
        "official_only",
        "limit",
    }


async def test_no_generic_provider_path_in_openapi():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    assert "/cards/{provider}" not in response.json()["paths"]
    assert "/cards" not in response.json()["paths"]
    assert "/cards/providers" not in response.json()["paths"]


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
    types = {action["type"] for action in response.json()["actions"]}
    assert "next_step" in types
    assert "load_cards" in types
    assert "raw" in types


def test_shared_action_catalog_matches_http_types():
    entries = build_action_catalog_entries()
    types = {entry["type"] for entry in entries}
    assert "next_step" in types
    assert "set_player_count" in types
    assert "load_cards" in types


async def test_get_global_actions_raw_ops_curated():
    async with make_client() as client:
        response = await client.get("/actions")
    ops = response.json()["raw_ops"]
    assert len(ops) > 10
    op_names = {op["op"] for op in ops}
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


async def test_openapi_card_schema_lists_expanded_fields():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["CardResult"]
    props = schema["properties"]
    assert "attributes" in props
