from __future__ import annotations

import pytest
from pydantic import ValidationError

from game_service.logic.actions import (
    MoveCardAction,
    DrawCardAction,
    LoadCardsAction,
    UnloadCardsAction,
    LoadCardItem,
    DealEncounterAction,
    DrawBoostAction,
)


def test_move_card_invalid_group_id_raises():
    # Use an obviously invalid group id
    with pytest.raises(ValidationError):
        MoveCardAction(instance_id="c1", dest_group_id="not_a_group")


def test_draw_card_invalid_player_n_raises():
    with pytest.raises(ValidationError):
        DrawCardAction(player_n="plr5", count=1)


def test_load_cards_invalid_load_group_raises():
    item = {"databaseId": "db-1", "loadGroupId": "invalid_group", "quantity": 1}
    with pytest.raises(ValidationError):
        LoadCardItem.model_validate(item)


def test_unload_cards_invalid_player_n_raises():
    with pytest.raises(ValidationError):
        UnloadCardsAction(player_n="nobody")


def test_deal_encounter_invalid_player_n_raises():
    with pytest.raises(ValidationError):
        DealEncounterAction(player_n="shared")


def test_draw_boost_invalid_player_n_raises():
    with pytest.raises(ValidationError):
        DrawBoostAction(player_n="shared")
