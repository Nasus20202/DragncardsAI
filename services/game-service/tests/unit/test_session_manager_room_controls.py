from __future__ import annotations

from unittest.mock import AsyncMock

from game_service.logic.action_catalog import build_action_catalog_entries

from .session_manager_test_support import make_session


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


def test_action_catalog_entries_include_player_count_once():
    entries = build_action_catalog_entries()
    player_count_entries = [
        entry for entry in entries if entry["type"] == "set_player_count"
    ]
    assert len(player_count_entries) == 1


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
