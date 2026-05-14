"""Unit tests for GameSession room event buffers and room control methods."""

from __future__ import annotations

from collections import deque
from unittest.mock import AsyncMock

from game_service.logic.action_catalog import build_action_catalog_entries

from ._game_session_test_helpers import fire_event, make_session


def test_alert_appended_on_send_alert_event():
    session = make_session()
    fire_event(session.channel, "send_alert", {"level": "info", "text": "hello"})
    assert len(session.get_alerts()) == 1
    assert session.get_alerts()[0]["text"] == "hello"


def test_alert_buffer_multiple_alerts():
    session = make_session()
    for i in range(5):
        fire_event(session.channel, "send_alert", {"level": "info", "text": str(i)})
    alerts = session.get_alerts()
    assert len(alerts) == 5
    assert [alert["text"] for alert in alerts] == ["0", "1", "2", "3", "4"]


def test_alert_buffer_evicts_at_maxlen_50():
    session = make_session()
    for i in range(55):
        fire_event(session.channel, "send_alert", {"text": str(i)})
    alerts = session.get_alerts()
    assert len(alerts) == 50
    assert alerts[0]["text"] == "5"
    assert alerts[-1]["text"] == "54"


def test_get_alerts_returns_copy():
    session = make_session()
    fire_event(session.channel, "send_alert", {"text": "x"})
    alerts = session.get_alerts()
    alerts.clear()
    assert len(session.get_alerts()) == 1


def test_alert_buffer_stays_bounded_if_internal_deque_replaced():
    session = make_session()
    session._alerts = deque(maxlen=2)

    fire_event(session.channel, "send_alert", {"text": "1"})
    fire_event(session.channel, "send_alert", {"text": "2"})
    fire_event(session.channel, "send_alert", {"text": "3"})

    assert [item["text"] for item in session.get_alerts()] == ["2", "3"]


def test_gui_update_stored_by_player_n():
    session = make_session()
    fire_event(
        session.channel,
        "gui_update",
        {"player_n": "player1", "prompt": "choose target"},
    )
    updates = session.get_gui_updates()
    assert "player1" in updates
    assert updates["player1"]["prompt"] == "choose target"


def test_gui_update_overwrites_previous_for_same_player():
    session = make_session()
    fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "first"})
    fire_event(
        session.channel, "gui_update", {"player_n": "player1", "prompt": "second"}
    )
    assert session.get_gui_updates()["player1"]["prompt"] == "second"


def test_gui_update_different_players_stored_separately():
    session = make_session()
    fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "p1"})
    fire_event(session.channel, "gui_update", {"player_n": "player2", "prompt": "p2"})
    updates = session.get_gui_updates()
    assert updates["player1"]["prompt"] == "p1"
    assert updates["player2"]["prompt"] == "p2"


def test_gui_update_payload_without_player_n_ignored():
    session = make_session()
    fire_event(session.channel, "gui_update", {"no_player_field": True})
    assert session.get_gui_updates() == {}


def test_get_gui_updates_returns_copy():
    session = make_session()
    fire_event(session.channel, "gui_update", {"player_n": "player1", "prompt": "x"})
    updates = session.get_gui_updates()
    updates.clear()
    assert "player1" in session.get_gui_updates()


def test_gui_update_ignores_non_dict_payload():
    session = make_session()
    fire_event(session.channel, "gui_update", "not-a-dict")
    assert session.get_gui_updates() == {}


async def test_reset_game_pushes_reset_game_event():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    state = await session.reset_game(save=False)
    calls = [call.args[0] for call in session.channel.push.await_args_list]
    assert "reset_game" in calls
    assert state == {"game": {}}


async def test_reset_game_with_save_flag():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    await session.reset_game(save=True)
    first_call = session.channel.push.await_args_list[0]
    assert first_call.args[0] == "reset_game"
    assert first_call.args[1] == {"options": {"save?": True}}


async def test_reset_game_reload_plugin_pushes_reset_and_reload():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(return_value={"game": {}})
    await session.reset_game(reload_plugin=True)
    first_call = session.channel.push.await_args_list[0]
    assert first_call.args[0] == "reset_and_reload"


async def test_set_seat_sends_message():
    session = make_session()
    session.room.send_room_event = AsyncMock()
    await session.set_seat(player_index=0, user_id=42)
    session.room.send_room_event.assert_awaited_once()
    call = session.room.send_room_event.await_args
    assert call.args[0] == "set_seat"
    assert call.args[1]["player_i"] == 0
    assert call.args[1]["new_user_id"] == 42
    assert "timestamp" in call.args[1]


async def test_set_spectator_sends_message():
    session = make_session()
    session.room.send_room_event = AsyncMock()
    await session.set_spectator(user_id=7, spectating=True)
    session.room.send_room_event.assert_awaited_once_with(
        "set_spectator", {"user_id": 7, "value": True}
    )


async def test_close_room_pushes_close_room():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.close_room()
    session.channel.push.assert_awaited_once()
    assert session.channel.push.await_args.args[0] == "close_room"


async def test_close_room_removes_from_manager():
    on_close = AsyncMock()
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    session.on_close = on_close
    await session.close_room()
    on_close.assert_awaited_once_with()


async def test_send_alert_pushes_send_alert():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.send_alert("watch out!")
    session.channel.push.assert_awaited_once()
    call = session.channel.push.await_args
    assert call.args[0] == "send_alert"
    assert call.args[1] == {"message": "watch out!"}


async def test_save_replay_pushes_save_replay():
    session = make_session()
    session.channel.push = AsyncMock(return_value={})
    await session.save_replay()
    session.channel.push.assert_awaited_once()
    call = session.channel.push.await_args
    assert call.args[0] == "save_replay"
    assert "timestamp" in call.args[1]


def test_action_catalog_entries_include_player_count_once():
    entries = build_action_catalog_entries()
    player_count_entries = [
        entry for entry in entries if entry["type"] == "set_player_count"
    ]
    assert len(player_count_entries) == 1
