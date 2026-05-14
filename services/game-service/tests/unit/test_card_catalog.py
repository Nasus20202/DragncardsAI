from __future__ import annotations

import pytest

from game_service.catalog.providers.base import CatalogProvider
from game_service.catalog.providers.registry import PROVIDERS
from game_service.catalog.service import (
    default_plugin_name,
    get_card_provider,
    get_load_groups,
    get_plugin_action_catalog,
    list_card_providers,
    normalize_search_filters,
    search_cards,
)

from .cards_test_support import install_stub_marvel_provider


@pytest.fixture(autouse=True)
def stub_marvel_provider(monkeypatch):
    install_stub_marvel_provider(monkeypatch)


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
    database_ids = [result.database_id for result in results]
    assert len(database_ids) == len(set(database_ids))


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


def test_search_cards_exposes_expanded_metadata_fields():
    result = search_cards(name="Black Panther", type_code="hero")[0]
    attributes = result.attributes.model_dump()
    assert "artificial_id" in attributes
    assert "id" in attributes
    assert "type" in attributes
    assert "unique" in attributes
    assert "rules" in attributes
    assert "set_number" in attributes


def test_search_cards_preserves_printing_level_metadata():
    result = search_cards(name="Black Panther", type_code="hero")[0]
    attributes = result.attributes.model_dump()
    assert attributes["pack_id"] is not None
    assert "pack_number" in attributes
    assert "unique_art" in attributes


def test_default_plugin_name_matches_registered_default_provider():
    provider = get_card_provider(default_plugin_name())
    assert provider["default"] is True
    assert provider["provider"] == default_plugin_name()


def test_normalize_search_filters_coerces_boolean_and_integer_values():
    normalized = normalize_search_filters(
        None,
        {"official_only": "false", "limit": "3", "name": "Spider-Man"},
    )

    assert normalized["official_only"] is False
    assert normalized["limit"] == 3
    assert normalized["name"] == "Spider-Man"


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
