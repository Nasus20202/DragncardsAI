"""
Unit tests for action translation (no network, no DragnCards needed).

These tests verify that translate_action() returns the correct DragnLang payload
structure for each action type.
"""

import pytest

from game_service.logic.actions import (
    DrawCardAction,
    ExhaustCardAction,
    ReadyCardAction,
    FlipCardAction,
    DealEncounterAction,
    DrawBoostAction,
    ShuffleIntoDeckAction,
    ZeroTokensAction,
    MoveCardAction,
    NextStepAction,
    RawAction,
    MulliganDrawHandAction,
    ShadowsOfThePastAction,
    PlayerEndPhaseAction,
    VillainEncounterPhaseAction,
    VillainEndPhaseAction,
    MultipleDoubleSidedVillainsAction,
    DiscardMinionAction,
    DiscardSideSchemeAction,
    ModifyTokensAction,
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


def test_translate_exhaust_card():
    action = ExhaustCardAction(instance_id="card-abc")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["EXHAUST_CARD", "card-abc"]


def test_translate_ready_card():
    action = ReadyCardAction(instance_id="card-xyz")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["READY_CARD", "card-xyz"]


def test_translate_flip_card():
    action = FlipCardAction(instance_id="card-123")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    # Flip cycles sides: A->B->C->A using COND
    assert payload["options"]["action_list"][0] == "COND"
    assert payload["options"]["action_list"][1] == [
        "DEFINED",
        "$GAME.cardById.card-123.sides.C",
    ]


def test_translate_deal_encounter_faceup():
    action = DealEncounterAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "dealEncounterFaceup"]
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_translate_deal_encounter_facedown():
    action = DealEncounterAction(player_n="player2", facedown=True)
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["ACTION_LIST", "dealEncounterFacedown"]
    assert payload["options"]["player_ui"] == {"playerN": "player2"}


def test_translate_draw_boost():
    action = DrawBoostAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "drawBoost"]
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


def test_translate_shuffle_into_deck():
    action = ShuffleIntoDeckAction(instance_id="card-456")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        ["VAR", "$DECK_GROUP_ID", "/cardById/card-456/deckGroupId"],
        ["MOVE_CARD", "card-456", "$DECK_GROUP_ID", 0],
        ["SHUFFLE_GROUP", "$DECK_GROUP_ID"],
    ]


def test_translate_zero_tokens():
    action = ZeroTokensAction(instance_id="card-789")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        ["SET", "/cardById/card-789/tokens", {}]
    ]


def test_translate_mulligan_draw_hand():
    action = MulliganDrawHandAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        ["COND", ["EQUAL", "$GAME.roundNumber", 0], [["LOG", "player1 mulliganed."]]],
        ["DRAW_HAND", "player1", "player1"],
    ]


def test_translate_deal_encounter_with_deck():
    action = DealEncounterAction(
        player_n="player1", facedown=False, deck_group_id="sharedEncounter2Deck"
    )
    payload = translate_action(action)
    assert payload["options"]["action_list"] == ["ACTION_LIST", "dealSecondFaceup"]


def test_translate_shadows_of_the_past():
    action = ShadowsOfThePastAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "shadowsOfThePast"]


def test_translate_player_end_phase():
    action = PlayerEndPhaseAction()
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "playerEndPhase"]


def test_translate_villain_encounter_phase():
    action = VillainEncounterPhaseAction()
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "villainEncounterPhase"]


def test_translate_villain_end_phase():
    action = VillainEndPhaseAction()
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "villainEndPhase"]


def test_translate_multiple_double_sided_villains():
    action = MultipleDoubleSidedVillainsAction()
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        "ACTION_LIST",
        "multipleDoubleSidedVillains",
    ]


def test_translate_discard_minion():
    action = DiscardMinionAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "discardMinion"]


def test_translate_discard_side_scheme():
    action = DiscardSideSchemeAction(player_n="player1")
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == ["ACTION_LIST", "discardSideScheme"]


def test_translate_modify_tokens_add():
    action = ModifyTokensAction(instance_id="card-123", token_type="threat", amount=2)
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        "INCREASE_VAL",
        "/cardById/card-123/tokens/threat",
        2,
    ]


def test_translate_modify_tokens_remove():
    action = ModifyTokensAction(instance_id="card-456", token_type="damage", amount=-1)
    payload = translate_action(action)
    assert payload["action"] == "evaluate"
    assert payload["options"]["action_list"] == [
        "INCREASE_VAL",
        "/cardById/card-456/tokens/damage",
        -1,
    ]
