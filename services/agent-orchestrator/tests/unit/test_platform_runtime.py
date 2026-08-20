from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from agent_orchestrator.runtime.platforms import (
    DEFAULT_PLATFORM,
    MARVEL_LCG_CATALOG_TOOLS,
    PLATFORM_MARVEL_LCG,
    platform_tool_sets,
)
from agent_orchestrator.runtime.seat_guard import check_seat_scope
from agent_orchestrator.runtime.seat_turn_guard import (
    PHASE_ADVANCING_TOOLS,
    SEAT_ACTION_TOOLS,
    check_turn_authority,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_system_prompt


def test_marvel_lcg_has_no_phase_advancing_tools_and_only_option_actions():
    tool_sets = platform_tool_sets(PLATFORM_MARVEL_LCG)

    assert tool_sets.phase_advancing == frozenset()
    assert tool_sets.seat_actions == frozenset({"choose_game_option"})


def test_marvel_lcg_catalog_tools_are_not_turn_sensitive_actions():
    tool_sets = platform_tool_sets(PLATFORM_MARVEL_LCG)

    assert MARVEL_LCG_CATALOG_TOOLS.isdisjoint(tool_sets.phase_advancing)
    assert MARVEL_LCG_CATALOG_TOOLS.isdisjoint(tool_sets.seat_actions)
    for tool_name in MARVEL_LCG_CATALOG_TOOLS:
        assert (
            check_turn_authority(
                caller_player_id="player1",
                tool_name=tool_name,
                phase="villain",
                platform=PLATFORM_MARVEL_LCG,
            )
            is None
        )


def test_dragncards_legacy_tool_sets_remain_the_default():
    tool_sets = platform_tool_sets(DEFAULT_PLATFORM)

    assert tool_sets.phase_advancing == PHASE_ADVANCING_TOOLS
    assert tool_sets.seat_actions == SEAT_ACTION_TOOLS


def test_phase_authority_uses_neutral_phase_and_pending_seats():
    assert (
        check_turn_authority(
            caller_player_id="player1",
            tool_name="choose_game_option",
            step_id=41,
            phase="player",
            phase_label="Player 1 Turn",
            pending_seats=["player1"],
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )
    violation = check_turn_authority(
        caller_player_id="player1",
        tool_name="choose_game_option",
        step_id=41,
        phase="player",
        phase_label="Player 1 Turn",
        pending_seats=["player2"],
        platform=PLATFORM_MARVEL_LCG,
    )
    assert violation is not None
    assert "not asking" in violation.message
    assert "Player 1 Turn" in violation.message


def test_pending_seat_is_authoritative_even_outside_player_phase():
    assert (
        check_turn_authority(
            caller_player_id="player1",
            tool_name="choose_game_option",
            step_id=41,
            phase="passive",
            phase_label="Resolve Setup",
            pending_seats=["player1"],
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )
    assert (
        check_turn_authority(
            caller_player_id="player1",
            tool_name="choose_game_option",
            phase="unknown",
            pending_seats=["player1"],
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_pending_seat_absence_is_a_finding_even_in_player_phase():
    violation = check_turn_authority(
        caller_player_id="player1",
        tool_name="choose_game_option",
        step_id=41,
        phase="player",
        phase_label="Player 2 Turn",
        pending_seats=["player2"],
        platform=PLATFORM_MARVEL_LCG,
    )

    assert violation is not None
    assert "not asking" in violation.message


def test_step_id_is_opaque_and_never_classifies_the_phase():
    assert (
        check_turn_authority(
            caller_player_id="player1",
            tool_name="choose_game_option",
            step_id="1.1",
            phase="villain",
            platform=PLATFORM_MARVEL_LCG,
        )
        is not None
    )
    assert (
        check_turn_authority(
            caller_player_id="player1",
            tool_name="choose_game_option",
            step_id="2.1",
            phase="player",
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_phase_finding_keeps_the_platform_phase_label():
    violation = check_turn_authority(
        caller_player_id="player1",
        tool_name="choose_game_option",
        step_id=42,
        phase="setup",
        phase_label="Resolve Mulligans",
        platform=PLATFORM_MARVEL_LCG,
    )

    assert violation is not None
    assert "Resolve Mulligans" in violation.message


def test_marvel_lcg_does_not_interpret_dragncards_group_names():
    assert (
        check_seat_scope(
            caller_player_id="player1",
            tool_name="choose_game_option",
            arguments={"target": "player2Hand"},
            platform=PLATFORM_MARVEL_LCG,
        )
        is None
    )


def test_marvel_lcg_resolves_target_ownership_from_normalised_zones():
    violation = check_seat_scope(
        caller_player_id="player1",
        tool_name="choose_game_option",
        arguments={"targets": ["object-2"]},
        platform=PLATFORM_MARVEL_LCG,
        game_state={
            "zones": {
                "player2Hand": [{"instanceId": "object-2", "name": "Hidden"}],
                "sharedVillain": [{"instanceId": "villain-1"}],
            }
        },
    )
    assert violation is not None
    assert violation.foreign_player_id == "player2"
    assert violation.argument == "targets[0]"


def test_default_system_prompt_is_unchanged_and_marvel_names_platform(tmp_path: Path):
    registry = SkillRegistry((tmp_path,))
    default = build_system_prompt(registry, [])
    marvel = build_system_prompt(registry, [], platform=PLATFORM_MARVEL_LCG)

    assert "played on the DragnCards digital tabletop" in default
    assert "played on the DragnCards digital tabletop" not in marvel
    assert "marvel-lcg" in marvel
    assert "list_game_options" in marvel
    assert "search_cards_marvel_champions" not in marvel
    assert "get_game_state_snapshot" not in marvel
    assert "export_game_state_snapshot" not in marvel


def test_session_platform_column_takes_precedence_over_legacy_metadata():
    from agent_orchestrator.runtime.platforms import session_platform

    session = SimpleNamespace(
        platform=PLATFORM_MARVEL_LCG,
        metadata_json={"platform": DEFAULT_PLATFORM},
    )
    assert session_platform(session) == PLATFORM_MARVEL_LCG
