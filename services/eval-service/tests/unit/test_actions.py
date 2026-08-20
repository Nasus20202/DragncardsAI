from __future__ import annotations

import json
from datetime import datetime, timezone

from eval_service.config import Settings
from eval_service.judge.actions import (
    DEFAULT_NON_STRATEGIC_ACTIONS,
    NON_STRATEGIC_ACTION_REASONS,
    non_strategic_reason,
    normalize_action_name,
    parse_action_set,
    recorded_action,
)
from eval_service.schemas.history import PLATFORM_MARVEL_LCG
from eval_service.schemas.history import StoredEvent

DEFAULT_SET = parse_action_set(DEFAULT_NON_STRATEGIC_ACTIONS)

# Every game-service action tool an agent can call. Kept explicit so a new tool
# added to the game-service shows up here as a deliberate classification rather
# than defaulting in unnoticed.
STRATEGIC_ACTIONS = (
    "deal_encounter",
    "discard_minion",
    "discard_side_scheme",
    "draw_boost",
    "draw_card",
    "exhaust_card",
    "flip_card",
    "modify_tokens",
    "move_card",
    "mulligan_draw_hand",
    "next_step",
    "player_end_phase",
    "prev_step",
    "raw_action",
    "ready_card",
    "set_card_property",
    "shadows_of_the_past",
    "shuffle_into_deck",
    "villain_encounter_phase",
    "villain_end_phase",
    "zero_tokens",
)


def test_searching_for_cards_cannot_be_wrong_but_taking_one_into_hand_can():
    # The reporter's own criterion, stated as a test: the line is whether the
    # action commits game state a player could get wrong, not whether the tool
    # touches cards.
    assert non_strategic_reason("search_cards_marvel_champions", DEFAULT_SET)
    assert non_strategic_reason("search_prebuilt_sets_marvel_champions", DEFAULT_SET)
    assert non_strategic_reason("draw_card", DEFAULT_SET) is None
    assert non_strategic_reason("move_card", DEFAULT_SET) is None


def test_every_strategic_action_is_evaluated():
    for action in STRATEGIC_ACTIONS:
        assert non_strategic_reason(action, DEFAULT_SET) is None, action


def test_non_strategic_actions_carry_a_stated_category():
    for action in DEFAULT_SET:
        reason = non_strategic_reason(action, DEFAULT_SET)
        assert reason and reason == NON_STRATEGIC_ACTION_REASONS[action], action


def test_unrecognised_action_is_evaluated_not_skipped():
    # Skipping a strategic action degrades evaluation silently, so anything the
    # taxonomy does not recognise must fall on the evaluate side.
    for action in ("play", "some_future_tool", "", None, 42, "search"):
        assert non_strategic_reason(action, DEFAULT_SET) is None


def test_namespaced_tool_alias_resolves_to_the_bare_name():
    assert normalize_action_name(
        "mcp__game-service__search_cards_marvel_champions"
    ) == ("search_cards_marvel_champions")
    assert non_strategic_reason(
        "mcp__game-service__search_cards_marvel_champions", DEFAULT_SET
    )
    # An unrelated tool that merely ENDS in a known name is not unwrapped.
    assert non_strategic_reason("rules_list_games", DEFAULT_SET) is None


def test_configured_list_replaces_the_default():
    settings = Settings(
        eval_judge_model="p/m", eval_non_strategic_actions="next_step, get_game_state"
    )
    skip = settings.non_strategic_actions
    assert non_strategic_reason("next_step", skip)
    # No longer skipped, because the configured list replaced the built-in one.
    assert non_strategic_reason("load_prebuilt_deck", skip) is None


def test_operator_added_action_is_skipped_with_an_honest_reason():
    skip = parse_action_set("some_house_rule_tool")
    assert non_strategic_reason("some_house_rule_tool", skip) == (
        "configured as non-strategic"
    )


def test_skipping_can_be_disabled_entirely():
    settings = Settings(eval_judge_model="p/m", eval_skip_non_strategic_moves=False)
    assert settings.non_strategic_actions == frozenset()
    assert (
        non_strategic_reason(
            "search_cards_marvel_champions", settings.non_strategic_actions
        )
        is None
    )


def test_marvel_option_taxonomy_uses_id_name_and_event_without_comma_splitting():
    identity = {"id": 7, "name": "Play, card", "event": "Player 1 Turn"}
    configured = parse_action_set(json.dumps(identity))

    assert len(configured) == 1
    assert non_strategic_reason(identity, configured, PLATFORM_MARVEL_LCG)
    # The same display name is a different engine choice when its id differs.
    assert (
        non_strategic_reason(
            {"id": 8, "name": "Play, card", "event": "Player 1 Turn"},
            configured,
            PLATFORM_MARVEL_LCG,
        )
        is None
    )
    assert (
        non_strategic_reason(
            {"id": 7, "name": "Play, card"},
            configured,
            PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_marvel_option_taxonomy_is_separate_from_dragncards_tool_names():
    assert (
        non_strategic_reason(
            "search_cards_marvel_champions",
            DEFAULT_SET,
            PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_marvel_recorded_action_is_additive_to_the_legacy_intended_action():
    identity = {"id": 7, "name": "Play", "event": "Turn"}
    assert (
        recorded_action(
            {"intended_action": "choose_option", "option_identity": identity},
            PLATFORM_MARVEL_LCG,
        )
        == identity
    )
    assert (
        recorded_action(
            {
                "intended_action": "choose_option",
                "arguments": {"option_identity": identity},
            },
            PLATFORM_MARVEL_LCG,
        )
        == identity
    )
    assert (
        recorded_action(
            {
                "intended_action": "choose_option",
                "marvel_lcg_option": identity,
            },
            PLATFORM_MARVEL_LCG,
        )
        == identity
    )
    assert (
        recorded_action({"intended_action": "move_card"}, PLATFORM_MARVEL_LCG)
        == "move_card"
    )


def test_settings_exposes_platform_specific_option_taxonomy():
    settings = Settings(
        eval_judge_model="p/m",
        eval_non_strategic_marvel_options='{"id":7,"name":"Play","event":"Turn"}',
    )
    assert len(settings.non_strategic_marvel_options) == 1


def test_orchestrator_marvel_option_envelope_reaches_recording_and_taxonomy():
    now = datetime.now(timezone.utc).isoformat()
    event = StoredEvent.model_validate(
        {
            "event_id": "evt-7",
            "game_id": "game-1",
            "platform": PLATFORM_MARVEL_LCG,
            "seq": 7,
            "envelope_version": 1,
            "actor": "agent",
            "event_type": "agent_move",
            "payload": {
                "intended_action": "choose_option",
                "marvel_lcg_option": {
                    "option_id": 7,
                    "option_name": "Play",
                    "event_type": "Player Turn",
                },
                "arguments": {"card_id": "ally-1"},
            },
            "occurred_at": now,
        }
    )
    expected = {"id": 7, "name": "Play", "event": "Player Turn"}

    action = recorded_action(event.payload, event.platform)
    configured = parse_action_set(json.dumps(expected))

    assert action == expected
    assert non_strategic_reason(action, configured, event.platform)
