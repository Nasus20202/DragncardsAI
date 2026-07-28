from __future__ import annotations

from eval_service.config import Settings
from eval_service.judge.actions import (
    DEFAULT_NON_STRATEGIC_ACTIONS,
    NON_STRATEGIC_ACTION_REASONS,
    non_strategic_reason,
    normalize_action_name,
    parse_action_set,
)

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
