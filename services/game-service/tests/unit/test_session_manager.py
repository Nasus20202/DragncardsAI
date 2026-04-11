"""
Unit tests for GameSession inbound event handling and outbound room control methods.

Pure tests — no network. Covers:
- BadGameStateError / StateUnavailableError flag detection via mocked channel broadcasts
- Alert buffer append, eviction at maxlen=50, and get_alerts()
- gui_update storage and overwrite per player_n, and get_gui_updates()
- reset_game, set_seat, set_spectator, close_room, send_alert, save_replay methods
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from game_service.phoenix_client.client import Channel, PhoenixClient, PhxMessage
from game_service.session.exceptions import (
    BadGameStateError,
    SessionError,
    StateUnavailableError,
)
from game_service.session.game_session import GameSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_channel() -> Channel:
    client = PhoenixClient("ws://localhost:4000/socket")
    return Channel(topic="room:test", join_ref="1", client=client)


def _make_session(channel: Channel | None = None) -> GameSession:
    if channel is None:
        channel = _make_channel()
    client = PhoenixClient("ws://localhost:4000/socket")
    return GameSession(
        session_id="test-session",
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug="test-room",
        created_at=datetime.now(timezone.utc),
        client=client,
        channel=channel,
    )


def _fire_event(channel: Channel, event: str, payload: dict) -> None:
    """Simulate a broadcast arriving on the channel."""
    msg = PhxMessage(
        join_ref="1", ref=None, topic="room:test", event=event, payload=payload
    )
    channel._handle(msg)


# ---------------------------------------------------------------------------
# 1.8 — BadGameStateError / StateUnavailableError flag detection
# ---------------------------------------------------------------------------


def test_bad_game_state_sets_flag():
    session = _make_session()
    assert not session._bad_state
    _fire_event(session.channel, "bad_game_state", {})
    assert session._bad_state


def test_unable_to_get_state_on_join_sets_flag():
    session = _make_session()
    assert not session._state_unavailable
    _fire_event(session.channel, "unable_to_get_state_on_join", {})
    assert session._state_unavailable


def test_unable_to_get_state_on_request_sets_flag():
    session = _make_session()
    _fire_event(session.channel, "unable_to_get_state_on_request", {})
    assert session._state_unavailable


async def test_get_state_raises_bad_game_state_error():
    session = _make_session()
    session._bad_state = True
    with pytest.raises(BadGameStateError):
        await session.get_state()


async def test_get_state_raises_state_unavailable_error():
    session = _make_session()
    session._state_unavailable = True
    with pytest.raises(StateUnavailableError):
        await session.get_state()


async def test_execute_action_raises_bad_game_state_before_push():
    from game_service.session.actions import NextStepAction

    session = _make_session()
    session._bad_state = True
    with pytest.raises(BadGameStateError):
        await session.execute_action(NextStepAction())


async def test_execute_action_raises_state_unavailable_before_push():
    from game_service.session.actions import NextStepAction

    session = _make_session()
    session._state_unavailable = True
    with pytest.raises(StateUnavailableError):
        await session.execute_action(NextStepAction())


# ---------------------------------------------------------------------------
# 1.9 — Alert buffer
# ---------------------------------------------------------------------------


def test_alert_appended_on_send_alert_event():
    session = _make_session()
    _fire_event(session.channel, "send_alert", {"level": "info", "text": "hello"})
    assert len(session.get_alerts()) == 1
    assert session.get_alerts()[0]["text"] == "hello"


def test_alert_buffer_multiple_alerts():
    session = _make_session()
    for i in range(5):
        _fire_event(session.channel, "send_alert", {"level": "info", "text": str(i)})
    alerts = session.get_alerts()
    assert len(alerts) == 5
    assert [a["text"] for a in alerts] == ["0", "1", "2", "3", "4"]


def test_alert_buffer_evicts_at_maxlen_50():
    session = _make_session()
    for i in range(55):
        _fire_event(session.channel, "send_alert", {"text": str(i)})
    alerts = session.get_alerts()
    assert len(alerts) == 50
    # Oldest (0–4) evicted, newest (5–54) remain
    assert alerts[0]["text"] == "5"
    assert alerts[-1]["text"] == "54"


def test_get_alerts_returns_copy():
    session = _make_session()
    _fire_event(session.channel, "send_alert", {"text": "x"})
    a1 = session.get_alerts()
    a1.clear()
    assert len(session.get_alerts()) == 1  # original deque unchanged


# ---------------------------------------------------------------------------
# 1.10 — GUI update storage
# ---------------------------------------------------------------------------


def test_gui_update_stored_by_player_n():
    session = _make_session()
    _fire_event(
        session.channel,
        "gui_update",
        {"player_n": "player1", "prompt": "choose target"},
    )
    updates = session.get_gui_updates()
    assert "player1" in updates
    assert updates["player1"]["prompt"] == "choose target"


def test_gui_update_overwrites_previous_for_same_player():
    session = _make_session()
    _fire_event(
        session.channel, "gui_update", {"player_n": "player1", "prompt": "first"}
    )
    _fire_event(
        session.channel, "gui_update", {"player_n": "player1", "prompt": "second"}
    )
    assert session.get_gui_updates()["player1"]["prompt"] == "second"


def test_gui_update_different_players_stored_separately():
    session = _make_session()
    _fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "p1"})
    _fire_event(session.channel, "gui_update", {"player_n": "player2", "prompt": "p2"})
    updates = session.get_gui_updates()
    assert updates["player1"]["prompt"] == "p1"
    assert updates["player2"]["prompt"] == "p2"


def test_gui_update_payload_without_player_n_ignored():
    session = _make_session()
    _fire_event(session.channel, "gui_update", {"no_player_field": True})
    assert session.get_gui_updates() == {}


def test_get_gui_updates_returns_copy():
    session = _make_session()
    _fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "x"})
    u1 = session.get_gui_updates()
    u1.clear()
    assert "player1" in session.get_gui_updates()


# ---------------------------------------------------------------------------
# 2.9 — Outbound room control methods (mocked Channel.push / client._send)
# ---------------------------------------------------------------------------


async def test_reset_game_pushes_reset_game_event():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    state = await session.reset_game(save=False)
    calls = [c.args[0] for c in session.channel.push.await_args_list]
    assert "reset_game" in calls
    assert state == {"game": {}}


async def test_reset_game_with_save_flag():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    await session.reset_game(save=True)
    first_call = session.channel.push.await_args_list[0]
    assert first_call.args[0] == "reset_game"
    assert first_call.args[1] == {"options": {"save?": True}}


async def test_reset_game_reload_plugin_pushes_reset_and_reload():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    await session.reset_game(reload_plugin=True)
    first_call = session.channel.push.await_args_list[0]
    assert first_call.args[0] == "reset_and_reload"


async def test_set_seat_sends_message():
    session = _make_session()
    session.client._send = AsyncMock()
    await session.set_seat(player_index=0, user_id=42)
    session.client._send.assert_awaited_once()
    msg = session.client._send.await_args.args[0]
    assert msg.event == "set_seat"
    assert msg.payload["player_i"] == 0
    assert msg.payload["new_user_id"] == 42
    assert "timestamp" in msg.payload


async def test_set_spectator_sends_message():
    session = _make_session()
    session.client._send = AsyncMock()
    await session.set_spectator(user_id=7, spectating=True)
    session.client._send.assert_awaited_once()
    msg = session.client._send.await_args.args[0]
    assert msg.event == "set_spectator"
    assert msg.payload == {"user_id": 7, "value": True}


async def test_close_room_pushes_close_room():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.close_room()
    session.channel.push.assert_awaited_once()
    assert session.channel.push.await_args.args[0] == "close_room"


async def test_close_room_removes_from_manager():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    mock_manager = MagicMock()
    mock_manager._remove_session = AsyncMock()
    session._manager = mock_manager
    await session.close_room()
    mock_manager._remove_session.assert_awaited_once_with("test-session")


async def test_send_alert_pushes_send_alert():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.send_alert("watch out!")
    session.channel.push.assert_awaited_once()
    call = session.channel.push.await_args
    assert call.args[0] == "send_alert"
    assert call.args[1] == {"message": "watch out!"}


async def test_save_replay_pushes_save_replay():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.save_replay()
    session.channel.push.assert_awaited_once()
    call = session.channel.push.await_args
    assert call.args[0] == "save_replay"
    assert "timestamp" in call.args[1]
