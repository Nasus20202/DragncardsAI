"""
Unit tests for game_service.session.actions

All tests are pure (no network, no DragnCards). They verify:
- translate_action() returns the correct DragnLang payload structure
- Each action type produces the right action_list and description
- RawAction is a passthrough
- SetCardPropertyAction builds the correct /cardById/... path
- MoveCardAction only appends dest_card_index when it is non-zero

DragnCards game_action payload structure (confirmed from frontend source):
  {
    "action": "evaluate",
    "options": {"action_list": [...], "description": "..."},
    "timestamp": <unix_ms>
  }
"""

import time

import pytest

from game_service.session.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    RawAction,
    SetCardPropertyAction,
    translate_action,
)


# ---------------------------------------------------------------------------
# translate_action structure
# ---------------------------------------------------------------------------


def test_translate_action_has_required_keys():
    action = NextStepAction()
    payload = translate_action(action)
    assert set(payload.keys()) == {"action", "options", "timestamp"}


def test_translate_action_no_player_ui_when_no_player_n():
    """Actions without a player_n (e.g. NextStepAction) must NOT include player_ui."""
    payload = translate_action(NextStepAction())
    assert "player_ui" not in payload["options"]


def test_translate_action_player_ui_included_when_player_n_present():
    """Actions with player_n must include player_ui so DragnCards resolves $PLAYER_N."""
    from game_service.session.actions import DrawCardAction

    payload = translate_action(DrawCardAction(player_n="player2", count=1))
    assert payload["options"]["player_ui"] == {"playerN": "player2"}


def test_translate_action_action_is_evaluate():
    """Top-level 'action' must always be the string 'evaluate'."""
    payload = translate_action(NextStepAction())
    assert payload["action"] == "evaluate"


def test_translate_action_timestamp_is_recent_ms():
    before = int(time.time() * 1000)
    payload = translate_action(NextStepAction())
    after = int(time.time() * 1000)
    assert before <= payload["timestamp"] <= after


def test_translate_action_options_has_description():
    payload = translate_action(NextStepAction())
    assert "description" in payload["options"]
    assert isinstance(payload["options"]["description"], str)


def test_translate_action_options_has_action_list():
    payload = translate_action(NextStepAction())
    assert "action_list" in payload["options"]
    assert isinstance(payload["options"]["action_list"], list)


# ---------------------------------------------------------------------------
# NextStepAction
# ---------------------------------------------------------------------------


def test_next_step_action_list():
    payload = translate_action(NextStepAction())
    assert payload["options"]["action_list"] == ["NEXT_STEP"]


def test_next_step_description():
    payload = translate_action(NextStepAction())
    assert "next" in payload["options"]["description"].lower()


# ---------------------------------------------------------------------------
# PrevStepAction
# ---------------------------------------------------------------------------


def test_prev_step_action_list():
    payload = translate_action(PrevStepAction())
    assert payload["options"]["action_list"] == ["PREV_STEP"]


def test_prev_step_description():
    payload = translate_action(PrevStepAction())
    assert (
        "prev" in payload["options"]["description"].lower()
        or "back" in payload["options"]["description"].lower()
    )


# ---------------------------------------------------------------------------
# DrawCardAction
# ---------------------------------------------------------------------------


def test_draw_card_default_values():
    action = DrawCardAction()
    assert action.player_n == "player1"
    assert action.count == 1


def test_draw_card_action_list():
    action = DrawCardAction(player_n="player1", count=3)
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["DRAW_CARD", 3]
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_draw_card_description_mentions_player_and_count():
    action = DrawCardAction(player_n="player2", count=5)
    payload = translate_action(action)
    desc = payload["options"]["description"]
    assert "player2" in desc
    assert "5" in desc


def test_draw_card_count_must_be_at_least_one():
    with pytest.raises(Exception):
        DrawCardAction(count=0)


# ---------------------------------------------------------------------------
# MoveCardAction
# ---------------------------------------------------------------------------


def test_move_card_action_list_basic():
    action = MoveCardAction(card_id="card-123", dest_group_id="player1Hand")
    payload = translate_action(action)
    assert payload["options"]["action_list"] == [
        "MOVE_CARD",
        "card-123",
        "player1Hand",
        -1,
    ]
    # No player_n set → no player_ui
    assert "player_ui" not in payload["options"]


def test_move_card_with_player_n_sets_player_ui():
    """player_n on MoveCardAction injects player_ui so automation rules resolve $PLAYER_N."""
    action = MoveCardAction(
        card_id="card-xyz", dest_group_id="player1Hand", player_n="player1"
    )
    payload = translate_action(action)
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_move_card_no_extra_index_when_dest_card_index_is_zero():
    action = MoveCardAction(
        card_id="c1", dest_group_id="g1", dest_stack_index=2, dest_card_index=0
    )
    payload = translate_action(action)
    assert len(payload["options"]["action_list"]) == 4


def test_move_card_appends_dest_card_index_when_nonzero():
    action = MoveCardAction(
        card_id="c1", dest_group_id="g1", dest_stack_index=0, dest_card_index=3
    )
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["MOVE_CARD", "c1", "g1", 0, 3]


def test_move_card_description_mentions_card_and_group():
    action = MoveCardAction(card_id="card-abc", dest_group_id="sharedDiscard")
    payload = translate_action(action)
    desc = payload["options"]["description"]
    assert "card-abc" in desc
    assert "sharedDiscard" in desc


# ---------------------------------------------------------------------------
# SetCardPropertyAction
# ---------------------------------------------------------------------------


def test_set_card_property_action_list():
    action = SetCardPropertyAction(card_id="c1", property_path="currentSide", value="B")
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["SET", "/cardById/c1/currentSide", "B"]


def test_set_card_property_with_numeric_value():
    action = SetCardPropertyAction(card_id="c2", property_path="tokens/damage", value=3)
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["SET", "/cardById/c2/tokens/damage", 3]


def test_set_card_property_description():
    action = SetCardPropertyAction(card_id="c1", property_path="currentSide", value="B")
    payload = translate_action(action)
    desc = payload["options"]["description"]
    assert "currentSide" in desc
    assert "c1" in desc


# ---------------------------------------------------------------------------
# RawAction
# ---------------------------------------------------------------------------


def test_raw_action_passthrough():
    action_list = ["CUSTOM_OP", "arg1", 42]
    action = RawAction(action_list=action_list, description="my op")
    payload = translate_action(action)
    assert payload["options"]["action_list"] == action_list
    assert payload["options"]["description"] == "my op"


def test_raw_action_default_description():
    action = RawAction(action_list=["NEXT_STEP"])
    assert action.description == "raw action"


def test_raw_action_can_wrap_next_step():
    action = RawAction(action_list=["NEXT_STEP"])
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["NEXT_STEP"]
