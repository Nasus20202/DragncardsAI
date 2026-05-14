"""Unit tests for GameSession state management, actions, and snapshots."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from game_service.logic.exceptions import (
    BadGameStateError,
    SessionError,
    SnapshotValidationError,
    StateUnavailableError,
)
from game_service.logic.snapshots import GameStateSnapshot

from ._game_session_test_helpers import fire_event, make_session


def test_bad_game_state_sets_flag():
    session = make_session()
    assert not session._bad_state
    fire_event(session.channel, "bad_game_state", {})
    assert session._bad_state


def test_unable_to_get_state_on_join_sets_flag():
    session = make_session()
    assert not session._state_unavailable
    fire_event(session.channel, "unable_to_get_state_on_join", {})
    assert session._state_unavailable


def test_unable_to_get_state_on_request_sets_flag():
    session = make_session()
    fire_event(session.channel, "unable_to_get_state_on_request", {})
    assert session._state_unavailable


async def test_get_state_returns_cached_state_when_not_stale():
    session = make_session()
    session._state = {"game": {"roundNumber": 1}}
    session.channel.push = AsyncMock()

    state = await session.get_state()

    assert state == {"game": {"roundNumber": 1}}
    session.channel.push.assert_not_awaited()


async def test_get_state_raises_bad_game_state_error():
    session = make_session()
    session._bad_state = True
    with pytest.raises(BadGameStateError):
        await session.get_state()


async def test_get_state_raises_state_unavailable_error():
    session = make_session()
    session._state_unavailable = True
    with pytest.raises(StateUnavailableError):
        await session.get_state()


async def test_get_state_fetches_fresh_state_without_deadlocking():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(
        return_value={"game": {"ok": True}}
    )

    state = await asyncio.wait_for(session.get_state(), timeout=1.0)

    assert state == {"game": {"ok": True}}
    session.channel.push.assert_awaited_once_with("request_state", {}, timeout=10.0)
    session.channel.wait_for_state_update.assert_awaited_once_with(timeout=10.0)


async def test_get_state_wraps_timeout_as_session_error():
    session = make_session()
    session.channel.push = AsyncMock(side_effect=asyncio.TimeoutError)

    with pytest.raises(SessionError, match="Could not fetch game state"):
        await session.get_state()


async def test_execute_action_raises_bad_game_state_before_push():
    from game_service.logic.actions import NextStepAction

    session = make_session()
    session._bad_state = True
    with pytest.raises(BadGameStateError):
        await session.execute_action(NextStepAction())


async def test_execute_action_raises_state_unavailable_before_push():
    from game_service.logic.actions import NextStepAction

    session = make_session()
    session._state_unavailable = True
    with pytest.raises(StateUnavailableError):
        await session.execute_action(NextStepAction())


async def test_execute_action_recovers_with_request_state_after_timeout():
    from game_service.logic.actions import NextStepAction

    session = make_session()
    session.channel.push = AsyncMock(side_effect=[{}, {"game": {"ok": True}}])
    session.channel.wait_for_event = AsyncMock(side_effect=asyncio.TimeoutError)
    session.channel.wait_for_state_update = AsyncMock(
        return_value={"game": {"ok": True}}
    )

    state = await session.execute_action(NextStepAction())

    assert state == {"game": {"ok": True}}
    assert session.channel.push.await_args_list[0].args[0] == "game_action"
    assert session.channel.push.await_args_list[1].args[0] == "request_state"
    session.channel.wait_for_state_update.assert_awaited_once()


async def test_execute_action_timeout_raises_when_recovery_also_times_out():
    from game_service.logic.actions import NextStepAction

    session = make_session()
    session.channel.push = AsyncMock(side_effect=[{}, {}])
    session.channel.wait_for_event = AsyncMock(side_effect=asyncio.TimeoutError)
    session.channel.wait_for_state_update = AsyncMock(side_effect=asyncio.TimeoutError)

    with pytest.raises(
        SessionError, match="Timed out waiting for state update after action"
    ):
        await session.execute_action(NextStepAction())


async def test_export_state_returns_snapshot_document():
    session = make_session()
    session._state = {"game": {"stepId": 0, "roundNumber": 1}}

    snapshot = await session.export_state()

    assert snapshot.schema_version == 1
    assert snapshot.plugin_name == "marvel-champions"
    assert snapshot.game["roundNumber"] == 1


async def test_export_state_raises_when_game_payload_missing():
    session = make_session()
    session._state = {"not_game": {}}

    with pytest.raises(SessionError, match="no exportable game payload"):
        await session.export_state()


async def test_load_state_pushes_set_game_and_refreshes_state():
    session = make_session()
    session.channel.push = AsyncMock(side_effect=[{}, {"game": {"roundNumber": 4}}])
    session.channel.wait_for_event = AsyncMock(
        return_value=MagicMock(event="state_update")
    )
    session.channel.wait_for_state_update = AsyncMock(
        return_value={"game": {"roundNumber": 4}}
    )

    state = await session.load_state(
        {
            "schema_version": 1,
            "plugin_name": "marvel-champions",
            "game": {"roundNumber": 4},
        }
    )

    assert state == {"game": {"roundNumber": 4}}
    first_call = session.channel.push.await_args_list[0]
    assert first_call.args[0] == "game_action"
    assert first_call.args[1]["action"] == "set_game"
    assert first_call.args[1]["options"]["game"] == {"roundNumber": 4}


async def test_load_state_accepts_snapshot_model():
    session = make_session()
    session.channel.push = AsyncMock(side_effect=[{}, {"game": {"roundNumber": 7}}])
    session.channel.wait_for_event = AsyncMock(
        return_value=MagicMock(event="state_update")
    )
    session.channel.wait_for_state_update = AsyncMock(
        return_value={"game": {"roundNumber": 7}}
    )

    state = await session.load_state(
        GameStateSnapshot(
            schema_version=1,
            plugin_name="marvel-champions",
            game={"roundNumber": 7},
        )
    )

    assert state["game"]["roundNumber"] == 7


async def test_load_state_rejects_wrong_plugin():
    session = make_session()

    with pytest.raises(SnapshotValidationError, match="does not match"):
        await session.load_state(
            {
                "schema_version": 1,
                "plugin_name": "other-game",
                "game": {},
            }
        )


async def test_load_state_rejects_unsupported_schema_version():
    session = make_session()

    with pytest.raises(
        SnapshotValidationError, match="Unsupported snapshot schema version"
    ):
        await session.load_state(
            {
                "schema_version": 999,
                "plugin_name": "marvel-champions",
                "game": {},
            }
        )
