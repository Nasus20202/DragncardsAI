"""
Unit tests for new action types (load_cards, unload_cards) in actions.py.
"""

from __future__ import annotations

import pytest

from game_service.session.actions import (
    LoadCardItem,
    LoadCardsAction,
    UnloadCardsAction,
    translate_action,
)


# ---------------------------------------------------------------------------
# LoadCardsAction
# ---------------------------------------------------------------------------


def test_load_cards_translate_single_card():
    action = LoadCardsAction(
        cards=[
            LoadCardItem(
                databaseId="c92a3f54-6113-5ef4-8a82-f8a366cf499c",
                loadGroupId="player1Deck",
                quantity=1,
            )
        ],
        description="Load Spider-Man",
    )
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    al = payload["options"]["action_list"]
    assert al[0] == "LOAD_CARDS"
    # Second element is ["LIST", {...card...}]
    load_list = al[1]
    assert load_list[0] == "LIST"
    assert load_list[1]["databaseId"] == "c92a3f54-6113-5ef4-8a82-f8a366cf499c"
    assert load_list[1]["loadGroupId"] == "player1Deck"
    assert load_list[1]["quantity"] == 1
    assert payload["options"]["description"] == "Load Spider-Man"
    # player_ui must be set so DragnCards resolves $PLAYER_N for playerN group templates
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_load_cards_translate_multiple_cards():
    action = LoadCardsAction(
        cards=[
            LoadCardItem(databaseId="uuid-1", loadGroupId="player1Deck", quantity=1),
            LoadCardItem(databaseId="uuid-2", loadGroupId="player1Deck", quantity=3),
            LoadCardItem(
                databaseId="uuid-3", loadGroupId="sharedEncounterDeck", quantity=1
            ),
        ],
    )
    payload = translate_action(action)
    al = payload["options"]["action_list"]
    assert al[0] == "LOAD_CARDS"
    load_list = al[1]
    assert load_list[0] == "LIST"
    assert len(load_list) == 4  # LIST + 3 cards
    assert load_list[2]["quantity"] == 3
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_load_cards_explicit_player_n():
    action = LoadCardsAction(
        cards=[LoadCardItem(databaseId="x", loadGroupId="playerNDeck", quantity=1)],
        player_n="player2",
    )
    payload = translate_action(action)
    assert payload["options"]["player_ui"] == {"playerN": "player2"}


def test_load_cards_default_player_n():
    action = LoadCardsAction(
        cards=[LoadCardItem(databaseId="x", loadGroupId="playerNDeck", quantity=1)]
    )
    assert action.player_n == "player1"


def test_load_cards_default_description():
    action = LoadCardsAction(
        cards=[LoadCardItem(databaseId="x", loadGroupId="player1Deck", quantity=1)]
    )
    assert action.description == "Load cards"


def test_load_card_item_alias():
    # Test both camelCase (API wire format) and snake_case (Python)
    item = LoadCardItem(databaseId="abc", loadGroupId="player1Deck", quantity=2)
    assert item.database_id == "abc"
    assert item.load_group_id == "player1Deck"
    assert item.quantity == 2


def test_load_card_item_quantity_default():
    item = LoadCardItem(databaseId="abc", loadGroupId="player1Deck")
    assert item.quantity == 1


def test_load_card_item_quantity_ge_one():
    with pytest.raises(Exception):
        LoadCardItem(databaseId="abc", loadGroupId="player1Deck", quantity=0)


# ---------------------------------------------------------------------------
# UnloadCardsAction
# ---------------------------------------------------------------------------


def test_unload_cards_player():
    action = UnloadCardsAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["UNLOAD_CARDS", "player1"]
    assert "player1" in payload["options"]["description"]
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_unload_cards_shared():
    action = UnloadCardsAction(player_n="shared")
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["UNLOAD_CARDS", "shared"]
    assert payload["options"]["player_ui"] == {"playerN": "shared"}


def test_unload_cards_all_players():
    for player in ("player1", "player2", "player3", "player4", "shared"):
        action = UnloadCardsAction(player_n=player)
        payload = translate_action(action)
        assert payload["options"]["action_list"] == ["UNLOAD_CARDS", player]
        assert payload["options"]["player_ui"] == {"playerN": player}
