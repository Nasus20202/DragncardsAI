from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx

from game_service.api.app import create_app
from game_service.catalog.providers.base import (
    CatalogCardAttributes,
    CatalogCardRecord,
    HotkeyAction,
    NamedActionList,
    PlayerCountLayout,
    PluginActionCatalog,
    TouchBarAction,
)
from game_service.catalog.providers.marvel_champions import (
    prebuilt_decks as prebuilt_decks_module,
)
from game_service.catalog.providers.marvel_champions import sets as sets_module
from game_service.catalog.providers.marvel_champions.sets import clear_sets_cache
from game_service.catalog.providers.registry import PROVIDERS
from game_service.logic.session_manager import SessionNotFoundError

SESSION_ID = "test-session-id"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def mock_session(plugin_name: str = "marvel-champions") -> MagicMock:
    session = MagicMock()
    session.session_id = SESSION_ID
    session.plugin_name = plugin_name
    return session


def mock_manager(session=None) -> MagicMock:
    manager = MagicMock()
    current_session = session or mock_session()

    async def get_session(sid):
        if sid == SESSION_ID:
            return current_session
        raise SessionNotFoundError(f"Session {sid!r} not found")

    manager.get_session = get_session
    manager.list_sessions = MagicMock(return_value=[])
    manager.load_prebuilt_deck = AsyncMock()
    return manager


def make_client(manager=None):
    app = create_app(session_manager=manager or mock_manager())
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


def stub_card_records() -> list[CatalogCardRecord]:
    return [
        CatalogCardRecord(
            database_id="11111111-1111-1111-1111-111111111111",
            name="Spider-Man",
            type_code="hero",
            classification="Justice",
            traits=["Avenger"],
            official=True,
            attributes=CatalogCardAttributes(
                artificial_id="spider-man-hero",
                id="spider-man",
                type="hero",
                unique=True,
                rules="Thwip thwip.",
                set_number="1",
                pack_id="core",
                pack_number="1",
                unique_art=False,
            ),
        ),
        CatalogCardRecord(
            database_id="22222222-2222-2222-2222-222222222222",
            name="Black Panther",
            type_code="hero",
            classification="Protection",
            traits=["Avenger", "King"],
            official=True,
            attributes=CatalogCardAttributes(
                artificial_id="black-panther-hero",
                id="black-panther",
                type="hero",
                unique=True,
                rules="Wakanda forever.",
                set_number="2",
                pack_id="core",
                pack_number="2",
                unique_art=True,
            ),
        ),
        CatalogCardRecord(
            database_id="33333333-3333-3333-3333-333333333333",
            name="Jessica Jones",
            type_code="ally",
            classification="Justice",
            traits=["Defender"],
            official=True,
            attributes=CatalogCardAttributes(
                artificial_id="jessica-jones-ally",
                id="jessica-jones",
                type="ally",
                unique=True,
                rules="Investigate.",
                set_number="3",
                pack_id="core",
                pack_number="3",
                unique_art=False,
            ),
        ),
        CatalogCardRecord(
            database_id="44444444-4444-4444-4444-444444444444",
            name="Nick Fury",
            type_code="ally",
            classification="Basic",
            traits=["Spy"],
            official=True,
            attributes=CatalogCardAttributes(
                artificial_id="nick-fury-ally",
                id="nick-fury",
                type="ally",
                unique=True,
                rules="Choose one.",
                set_number="4",
                pack_id="core",
                pack_number="4",
                unique_art=False,
            ),
        ),
        CatalogCardRecord(
            database_id="55555555-5555-5555-5555-555555555555",
            name="Iron Man",
            type_code="hero",
            classification="Leadership",
            traits=["Avenger"],
            official=False,
            attributes=CatalogCardAttributes(
                artificial_id="iron-man-hero",
                id="iron-man",
                type="hero",
                unique=True,
                rules="Powered armor.",
                set_number="5",
                pack_id="expansion",
                pack_number="5",
                unique_art=False,
            ),
        ),
    ]


def stub_plugin_action_catalog() -> PluginActionCatalog:
    return PluginActionCatalog(
        named_action_lists=[
            NamedActionList(id="toggleExhaust", action_list=["toggle"])
        ],
        hotkeys=[HotkeyAction(scope="game", key="D", label="Draw")],
        touch_bar=[
            TouchBarAction(
                id="drawCard",
                row=0,
                order=0,
                action_type="game",
                label="Draw",
            )
        ],
        player_count_layouts=[
            PlayerCountLayout(label="2", num_players=2, layout_id="standard2Player")
        ],
        load_groups=[
            "playerNDeck",
            "sharedEncounterDeck",
            "sharedVillain",
            "sharedVillainDiscard",
            "playerNOutOfPlay",
        ],
    )


def stub_set_records() -> list[dict[str, str]]:
    return [
        {"id": "set-001", "name": "Spider-Verse", "type": "Hero Set"},
        {"id": "set-002", "name": "Sinister Syndicate", "type": "Modular Set"},
        {"id": "set-003", "name": "Valkyrie Nemesis", "type": "Nemesis Set"},
    ]


def stub_prebuilt_decks() -> dict[str, dict[str, object]]:
    return {
        "deck-001": {
            "label": "Spider-Man Starter",
            "cards": [
                {
                    "databaseId": "11111111-1111-1111-1111-111111111111",
                    "loadGroupId": "playerNDeck",
                    "quantity": 1,
                }
            ],
            "postLoadActionList": None,
        }
    }


def install_stub_marvel_provider(monkeypatch) -> None:
    clear_sets_cache()
    prebuilt_decks_module.load_prebuilt_decks.cache_clear()
    records = stub_card_records()
    provider = PROVIDERS["marvel-champions"]
    action_catalog = stub_plugin_action_catalog()
    set_records = stub_set_records()
    prebuilt_decks = {
        record["id"]: {
            "id": record["id"],
            "deck_id": f'{record["name"]} ({record["type"].replace(" Set", "")})',
            "label": record["name"],
            "type": record["type"],
        }
        for record in set_records
    }

    def fake_search_cards(filters):
        normalized_name = str(filters.get("name", "")).lower()
        normalized_type = str(filters.get("type_code", "")).lower()
        normalized_classification = str(filters.get("classification", "")).lower()
        official_only = filters.get("official_only", True)
        limit = int(filters.get("limit", 50))

        results = []
        for record in records:
            if normalized_name and normalized_name not in record.name.lower():
                continue
            if normalized_type and (record.type_code or "").lower() != normalized_type:
                continue
            if (
                normalized_classification
                and normalized_classification
                not in (record.classification or "").lower()
            ):
                continue
            if official_only and not record.official:
                continue
            results.append(record)
        return results[:limit]

    monkeypatch.setattr(provider, "search_cards", fake_search_cards)
    monkeypatch.setattr(provider, "load_card_db", lambda: list(records))
    monkeypatch.setattr(
        provider, "get_load_groups", lambda: list(action_catalog.load_groups)
    )
    monkeypatch.setattr(provider, "get_action_catalog", lambda: action_catalog)
    monkeypatch.setattr(provider, "load_sets", lambda: list(set_records))
    monkeypatch.setattr(sets_module, "load_sets", lambda: list(set_records))
    monkeypatch.setattr(prebuilt_decks_module, "load_sets", lambda: list(set_records))
    monkeypatch.setattr(
        prebuilt_decks_module,
        "load_prebuilt_decks",
        lambda: dict(prebuilt_decks),
    )
    monkeypatch.setattr(
        prebuilt_decks_module,
        "get_prebuilt_deck_by_id",
        lambda deck_id: prebuilt_decks.get(deck_id),
    )

    def fake_search_sets(name=None, type=None):
        normalized_name = str(name or "").lower()
        normalized_type = str(type or "").lower()
        results = []
        for record in set_records:
            if normalized_name and normalized_name not in record["name"].lower():
                continue
            if normalized_type and record["type"].lower() != normalized_type:
                continue
            results.append(record)
        return results

    monkeypatch.setattr(provider, "search_sets", fake_search_sets)
