from __future__ import annotations

from agent_orchestrator.runtime.game_session_guard import (
    GameSessionBindingViolation,
    check_game_session_binding,
)


def test_matching_game_id_is_allowed() -> None:
    assert (
        check_game_session_binding(
            assignment="game-service",
            tool_name="game-service_get_game_state",
            arguments={"session_id": "game-a"},
            bound_game_id="game-a",
        )
        is None
    )


def test_different_game_id_is_refused_without_echoing_identifiers() -> None:
    violation = check_game_session_binding(
        assignment="game-service",
        tool_name="game-service_get_game_state",
        arguments={"session_id": "game-b"},
        bound_game_id="game-a",
    )

    assert isinstance(violation, GameSessionBindingViolation)
    assert "game-a" not in violation.message
    assert "game-b" not in violation.message


def test_unbound_session_can_make_first_discovery_call() -> None:
    assert (
        check_game_session_binding(
            assignment="game-service",
            tool_name="game-service_next_step",
            arguments={"session_id": "game-b"},
            bound_game_id=None,
        )
        is None
    )


def test_non_game_service_call_is_not_game_bound() -> None:
    assert (
        check_game_session_binding(
            assignment="builtin",
            tool_name="some_builtin",
            arguments={"session_id": "game-b"},
            bound_game_id="game-a",
        )
        is None
    )


def test_call_without_existing_game_id_is_left_to_service_validation() -> None:
    assert (
        check_game_session_binding(
            assignment="game-service",
            tool_name="game-service_next_step",
            arguments={},
            bound_game_id="game-a",
        )
        is None
    )
