"""
Unit tests for card catalog logic and GET /cards HTTP endpoints.
"""

from __future__ import annotations

import pytest

from game_service.catalog.providers.base import CatalogProvider
from game_service.catalog.providers.registry import PROVIDERS
from game_service.catalog.service import (
    get_card_provider,
    get_load_groups,
    get_plugin_action_catalog,
    list_card_providers,
    search_cards,
)

from ._api_test_helpers import make_client

# ---------------------------------------------------------------------------
# Card catalog search unit tests (pure logic)
# ---------------------------------------------------------------------------


def test_search_cards_by_name_returns_results():
    results = search_cards(name="Spider-Man", type_code="hero")
    assert len(results) > 0
    for result in results:
        assert "spider-man" in result.name.lower()
        assert result.type_code == "hero"


def test_search_cards_returns_database_id():
    results = search_cards(name="Black Panther", type_code="hero")
    assert len(results) > 0
    for result in results:
        assert len(result.database_id) == 36
        assert result.database_id.count("-") == 4


def test_search_cards_type_filter():
    results = search_cards(name="Spider-Man", type_code="villain")
    for result in results:
        assert result.type_code == "villain"


def test_search_cards_classification_filter():
    results = search_cards(type_code="ally", classification="Justice", limit=5)
    for result in results:
        assert result.type_code == "ally"
        assert "justice" in (result.classification or "").lower()


def test_search_cards_limit_respected():
    results = search_cards(type_code="ally", limit=3)
    assert len(results) <= 3


def test_search_cards_deduplicates_by_database_id():
    results = search_cards(name="Iron Man")
    db_ids = [result.database_id for result in results]
    assert len(db_ids) == len(set(db_ids)), "No duplicate databaseIds in results"


def test_search_cards_official_only_default():
    results = search_cards(name="Spider-Man", type_code="hero")
    for result in results:
        assert result.official is True


def test_search_cards_empty_query_returns_up_to_limit():
    results = search_cards(limit=10)
    assert len(results) <= 10


def test_search_cards_unknown_plugin_returns_empty_list():
    with pytest.raises(ValueError, match="Unknown card provider"):
        search_cards(plugin_name="unknown-plugin")


def test_list_card_providers_exposes_filters():
    providers = list_card_providers()
    assert len(providers) >= 1
    marvel = next(
        provider for provider in providers if provider["provider"] == "marvel-champions"
    )
    filter_names = {item["name"] for item in marvel["filters"]}
    assert filter_names >= {
        "name",
        "type_code",
        "classification",
        "official_only",
        "limit",
    }


def test_registered_provider_uses_explicit_interface():
    assert isinstance(PROVIDERS["marvel-champions"], CatalogProvider)


def test_get_card_provider_exposes_load_groups():
    provider = get_card_provider("marvel-champions")
    assert "playerNDeck" in provider["load_groups"]
    assert "sharedVillain" in provider["load_groups"]
    assert "sharedVillainDiscard" in provider["load_groups"]
    assert "playerNOutOfPlay" in provider["load_groups"]


def test_get_plugin_action_catalog_exposes_marvel_metadata():
    catalog = get_plugin_action_catalog("marvel-champions")
    assert "playerNDeck" in catalog.load_groups
    assert "sharedVillainDiscard" in catalog.load_groups
    assert any(item.id == "toggleExhaust" for item in catalog.named_action_lists)
    assert any(item.scope == "game" and item.key == "D" for item in catalog.hotkeys)
    assert any(item.id == "drawCard" for item in catalog.touch_bar)
    assert any(
        item.label == "2" and item.layout_id == "standard2Player"
        for item in catalog.player_count_layouts
    )


def test_get_load_groups_unknown_plugin_returns_empty_list():
    assert get_load_groups("unknown-plugin") == []


def test_get_plugin_action_catalog_unknown_plugin_returns_empty_metadata():
    catalog = get_plugin_action_catalog("unknown-plugin")
    assert catalog.load_groups == []
    assert catalog.named_action_lists == []
    assert catalog.hotkeys == []


def test_search_cards_exposes_expanded_metadata_fields():
    result = search_cards(name="Black Panther", type_code="hero")[0]
    attributes = result.attributes.model_dump()
    expected_fields = {
        "artificial_id",
        "id",
        "type",
        "unique",
        "rules",
        "set_number",
    }
    assert expected_fields.issubset(attributes.keys())


def test_search_cards_preserves_printing_level_metadata():
    result = search_cards(name="Black Panther", type_code="hero")[0]
    attributes = result.attributes.model_dump()
    assert attributes["pack_id"] is not None
    assert "pack_number" in attributes
    assert "unique_art" in attributes


# ---------------------------------------------------------------------------
# GET /cards/{provider} HTTP endpoint tests
# ---------------------------------------------------------------------------


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
    expected_fields = {"artificial_id", "id", "type", "rules", "unique"}
    assert expected_fields.issubset(card["attributes"].keys())


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
    paths = response.json()["paths"]
    assert "/cards/{provider}" not in paths
    assert "/cards" not in paths
    assert "/cards/providers" not in paths


async def test_openapi_card_schema_lists_expanded_fields():
    async with make_client() as client:
        response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()["components"]["schemas"]["CardResult"]
    assert "attributes" in schema["properties"]
