"""
Unit tests for action translation (no network, no DragnCards needed).

These tests verify that translate_action() returns the correct DragnLang payload
structure for each action type.
"""

import pytest

from game_service.logic.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    RawAction,
    translate_action,
)


def test_translate_move_card():
    action = MoveCardAction(
        instance_id="card-1", dest_group_id="player1Hand", dest_stack_index=-1
    )
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        "MOVE_CARD",
        "card-1",
        "player1Hand",
        -1,
    ]
    assert "description" in payload["options"]
    assert "timestamp" in payload


def test_translate_draw_card():
    action = DrawCardAction(player_n="player1", count=3)
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["DRAW_CARD", 3]
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_translate_next_step():
    payload = translate_action(NextStepAction())
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["NEXT_STEP"]


def test_translate_raw():
    raw = ["SOME_FUNC", "arg1", 42]
    action = RawAction(action_list=raw, description="test raw")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == raw
    assert payload["options"]["description"] == "test raw"
