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
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from game_service.coordination.session_store import InMemorySessionStore
from game_service.logic.exceptions import (
    AmbiguousSessionIdentifierError,
    BadGameStateError,
    SessionError,
    SessionLockedError,
    SessionNotFoundError,
    SnapshotValidationError,
    StateUnavailableError,
)
from game_service.logic.session import GameSession
from game_service.logic.session_manager import SessionManager
from game_service.phoenix_client.client import Channel, PhoenixClient, PhxMessage

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


def _make_manager() -> SessionManager:
    return SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
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


async def test_get_state_fetches_fresh_state_without_deadlocking():
    session = _make_session()
    session.channel.push = AsyncMock(return_value={})
    session.channel.wait_for_state_update = AsyncMock(
        return_value={"game": {"ok": True}}
    )

    state = await asyncio.wait_for(session.get_state(), timeout=1.0)

    assert state == {"game": {"ok": True}}
    session.channel.push.assert_awaited_once_with("request_state", {}, timeout=10.0)
    session.channel.wait_for_state_update.assert_awaited_once_with(timeout=10.0)


async def test_execute_action_raises_bad_game_state_before_push():
    from game_service.logic.actions import NextStepAction

    session = _make_session()
    session._bad_state = True
    with pytest.raises(BadGameStateError):
        await session.execute_action(NextStepAction())


async def test_execute_action_raises_state_unavailable_before_push():
    from game_service.logic.actions import NextStepAction

    session = _make_session()
    session._state_unavailable = True
    with pytest.raises(StateUnavailableError):
        await session.execute_action(NextStepAction())


async def test_execute_action_recovers_with_request_state_after_timeout():
    from game_service.logic.actions import NextStepAction

    session = _make_session()
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

    session = _make_session()
    session.channel.push = AsyncMock(side_effect=[{}, {}])
    session.channel.wait_for_event = AsyncMock(side_effect=asyncio.TimeoutError)
    session.channel.wait_for_state_update = AsyncMock(side_effect=asyncio.TimeoutError)

    with pytest.raises(
        SessionError, match="Timed out waiting for state update after action"
    ):
        await session.execute_action(NextStepAction())


async def test_export_state_returns_snapshot_document():
    session = _make_session()
    session._state = {"game": {"stepId": 0, "roundNumber": 1}}

    snapshot = await session.export_state()

    assert snapshot.schema_version == 1
    assert snapshot.plugin_name == "marvel-champions"
    assert snapshot.game["roundNumber"] == 1


async def test_load_state_pushes_set_game_and_refreshes_state():
    session = _make_session()
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


async def test_load_state_rejects_wrong_plugin():
    session = _make_session()

    with pytest.raises(SnapshotValidationError, match="does not match"):
        await session.load_state(
            {
                "schema_version": 1,
                "plugin_name": "other-game",
                "game": {},
            }
        )


async def test_load_state_rejects_unsupported_schema_version():
    session = _make_session()

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
    await session.set_seat(player_id="player2", user_id=42)
    session.client._send.assert_awaited_once()
    msg = session.client._send.await_args.args[0]
    assert msg.event == "set_seat"
    assert msg.payload["player_i"] == "player2"
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
    on_close = AsyncMock()
    session.on_close = on_close
    await session.close_room()
    on_close.assert_awaited_once_with()


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


# ---------------------------------------------------------------------------
# Auto-seat helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_auto_seat_assigns_first_available_player():
    manager = _make_manager()
    session = _make_session()
    session.get_state = AsyncMock(
        return_value={
            "game": {
                "playerInfo": {
                    "player1": {"id": 10},
                    "player2": None,
                    "player3": {"id": None},
                }
            }
        }
    )
    session.set_seat = AsyncMock()

    await manager._auto_seat(session, user_id=42)

    session.set_seat.assert_awaited_once_with(player_id="player2", user_id=42)


@pytest.mark.asyncio
async def test_auto_seat_skips_when_user_already_seated():
    manager = _make_manager()
    session = _make_session()
    session.get_state = AsyncMock(
        return_value={"game": {"playerInfo": {"player1": {"id": 42}, "player2": None}}}
    )
    session.set_seat = AsyncMock()

    await manager._auto_seat(session, user_id=42)

    session.set_seat.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_seat_falls_back_to_player_data():
    manager = _make_manager()
    session = _make_session()
    session.get_state = AsyncMock(
        return_value={
            "game": {
                "playerData": {
                    "player1": {"user_id": 10},
                    "player2": {"user_id": None},
                    "player3": {},
                }
            }
        }
    )
    session.set_seat = AsyncMock()

    await manager._auto_seat(session, user_id=42)

    session.set_seat.assert_awaited_once_with(player_id="player2", user_id=42)


# ---------------------------------------------------------------------------
# Session identification: a UUID `session_id` OR a human-readable room slug.
#
# `resolve_session_id` is the single shared resolver behind every
# session-identifying path (state reads, mutations, and delete), so an operator or
# an agent can address a session as `lively-fog-1234` instead of a UUID.
# ---------------------------------------------------------------------------

_TEST_SESSION_UUID = "11111111-1111-1111-1111-111111111111"
_TEST_ROOM_SLUG = "lively-fog-1234"


def _make_manager_with_store(store: InMemorySessionStore) -> SessionManager:
    return SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
    )


def _make_uuid_session() -> GameSession:
    client = PhoenixClient("ws://localhost:4000/socket")
    channel = _make_channel()
    return GameSession(
        session_id=_TEST_SESSION_UUID,
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug=_TEST_ROOM_SLUG,
        created_at=datetime.now(timezone.utc),
        client=client,
        channel=channel,
    )


async def _register(manager: SessionManager, session: GameSession) -> None:
    await manager._session_store.put_session(session.to_metadata())
    manager._sessions[session.session_id] = session


# --- Slug metadata lookup ---


@pytest.mark.asyncio
async def test_lookup_session_by_slug_returns_session_metadata():
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    metadata = await manager.lookup_session_by_slug(_TEST_ROOM_SLUG)

    assert metadata["session_id"] == _TEST_SESSION_UUID
    assert metadata["room_slug"] == _TEST_ROOM_SLUG


@pytest.mark.asyncio
async def test_lookup_session_by_slug_resolves_via_store_only():
    # No live session in the pool — slug must still resolve from the store index.
    store = InMemorySessionStore()
    session = _make_uuid_session()
    await store.put_session(session.to_metadata())
    manager = _make_manager_with_store(store)

    metadata = await manager.lookup_session_by_slug(_TEST_ROOM_SLUG)

    assert metadata["session_id"] == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_lookup_session_by_slug_unknown_slug_raises_not_found():
    manager = _make_manager_with_store(InMemorySessionStore())
    with pytest.raises(SessionNotFoundError):
        await manager.lookup_session_by_slug("no-such-room")


# --- Shared identifier resolution ---


@pytest.mark.asyncio
async def test_resolve_session_id_passes_through_canonical_uuid():
    manager = _make_manager_with_store(InMemorySessionStore())

    # No store round-trip is needed: a well-formed UUID is its own answer, which
    # is what keeps an already-removed session resolvable (idempotent delete).
    assert await manager.resolve_session_id(_TEST_SESSION_UUID) == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_resolve_session_id_normalizes_non_canonical_uuid():
    manager = _make_manager_with_store(InMemorySessionStore())

    resolved = await manager.resolve_session_id("{" + _TEST_SESSION_UUID.upper() + "}")

    assert resolved == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_resolve_session_id_resolves_slug_from_the_pool():
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    assert await manager.resolve_session_id(_TEST_ROOM_SLUG) == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_resolve_session_id_resolves_slug_from_the_store_index():
    # Session not loaded in this process's pool — the store's slug index answers.
    store = InMemorySessionStore()
    await store.put_session(_make_uuid_session().to_metadata())
    manager = _make_manager_with_store(store)

    assert await manager.resolve_session_id(_TEST_ROOM_SLUG) == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_resolve_session_id_unknown_identifier_raises_not_found():
    manager = _make_manager_with_store(InMemorySessionStore())

    with pytest.raises(SessionNotFoundError):
        await manager.resolve_session_id("no-such-room")


@pytest.mark.asyncio
async def test_resolve_session_id_ambiguous_slug_raises():
    # `attach_session` may create several sessions for one DragnCards room, so a
    # slug is not guaranteed to identify exactly one session.
    manager = _make_manager_with_store(InMemorySessionStore())
    first = _make_uuid_session()
    second = _make_uuid_session()
    second.session_id = "22222222-2222-2222-2222-222222222222"
    await _register(manager, first)
    manager._sessions[second.session_id] = second

    with pytest.raises(AmbiguousSessionIdentifierError) as excinfo:
        await manager.resolve_session_id(_TEST_ROOM_SLUG)

    assert _TEST_SESSION_UUID in str(excinfo.value)
    assert second.session_id in str(excinfo.value)


@pytest.mark.asyncio
async def test_resolve_session_id_ignores_stale_slug_index_entry():
    store = InMemorySessionStore()
    await store.put_session(_make_uuid_session().to_metadata())
    # Drop the record but leave the slug index pointing at it.
    store._records.pop(_TEST_SESSION_UUID)
    manager = _make_manager_with_store(store)

    with pytest.raises(SessionNotFoundError):
        await manager.resolve_session_id(_TEST_ROOM_SLUG)


# --- State/mutation/delete paths accept either form ---


@pytest.mark.asyncio
async def test_get_session_returns_session_by_uuid():
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    session = await manager.get_session(_TEST_SESSION_UUID)

    assert session.session_id == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_get_session_normalizes_non_canonical_uuid():
    # A valid-but-non-canonical UUID (uppercase) must still match the stored id.
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    session = await manager.get_session(_TEST_SESSION_UUID.upper())

    assert session.session_id == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_get_session_returns_session_by_room_slug():
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    session = await manager.get_session(_TEST_ROOM_SLUG)

    assert session.session_id == _TEST_SESSION_UUID


@pytest.mark.asyncio
async def test_get_session_unknown_uuid_raises_not_found():
    manager = _make_manager_with_store(InMemorySessionStore())
    with pytest.raises(SessionNotFoundError):
        await manager.get_session("00000000-0000-0000-0000-000000000000")


@pytest.mark.asyncio
async def test_delete_session_by_uuid_removes_index_entry():
    manager = _make_manager_with_store(InMemorySessionStore())
    session = _make_uuid_session()
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    await manager.delete_session(_TEST_SESSION_UUID)

    assert _TEST_SESSION_UUID not in manager._sessions
    assert await manager._session_store.get_session(_TEST_SESSION_UUID) is None
    assert await manager._session_store.get_session_id_by_slug(_TEST_ROOM_SLUG) is None


@pytest.mark.asyncio
async def test_delete_session_by_room_slug_removes_the_session():
    manager = _make_manager_with_store(InMemorySessionStore())
    session = _make_uuid_session()
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    await manager.delete_session(_TEST_ROOM_SLUG)

    assert _TEST_SESSION_UUID not in manager._sessions
    assert await manager._session_store.get_session(_TEST_SESSION_UUID) is None
    assert await manager._session_store.get_session_id_by_slug(_TEST_ROOM_SLUG) is None


@pytest.mark.asyncio
async def test_session_operation_lock_shares_one_key_for_uuid_and_slug():
    # A slug-addressed and a UUID-addressed operation must contend for the same
    # lock, so resolution has to happen before the lock key is derived.
    manager = _make_manager_with_store(InMemorySessionStore())
    await _register(manager, _make_uuid_session())

    async with manager.session_operation_lock(_TEST_ROOM_SLUG):
        with pytest.raises(SessionLockedError):
            async with manager.session_operation_lock(
                _TEST_SESSION_UUID, wait_timeout=0.05
            ):
                pass


# ---------------------------------------------------------------------------
# Ephemeral reconstruction reaper
# ---------------------------------------------------------------------------


def _make_ephemeral_session(
    *, session_id: str, room_slug: str, created_at: datetime
) -> GameSession:
    client = PhoenixClient("ws://localhost:4000/socket")
    channel = _make_channel()
    return GameSession(
        session_id=session_id,
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug=room_slug,
        created_at=created_at,
        client=client,
        channel=channel,
        ephemeral=True,
    )


@pytest.mark.asyncio
async def test_reaper_deletes_expired_ephemeral_session_and_room():
    store = InMemorySessionStore()
    manager = SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
        ephemeral_session_ttl_seconds=1800.0,
    )
    # Created well past the TTL.
    created = datetime.now(timezone.utc) - timedelta(seconds=3600)
    session = _make_ephemeral_session(
        session_id="22222222-2222-2222-2222-222222222222",
        room_slug="aged-room-1",
        created_at=created,
    )
    session.channel.push = AsyncMock(return_value={})
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    reaped = await manager.reap_expired_ephemeral_sessions()

    assert reaped == 1
    # The session AND its DragnCards room are reclaimed: leaving the channel only
    # detaches this client, so the room itself must be closed as well.
    assert session.channel.push.await_args.args[0] == "close_room"
    session.client.leave.assert_awaited_once()
    session.client.disconnect.assert_awaited_once()
    assert session.session_id not in manager._sessions
    assert await store.get_session(session.session_id) is None
    assert await store.get_session_id_by_slug("aged-room-1") is None


@pytest.mark.asyncio
async def test_reaper_does_not_touch_fresh_ephemeral_session():
    store = InMemorySessionStore()
    manager = SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
        ephemeral_session_ttl_seconds=1800.0,
    )
    session = _make_ephemeral_session(
        session_id="33333333-3333-3333-3333-333333333333",
        room_slug="fresh-room-1",
        created_at=datetime.now(timezone.utc),  # well within TTL
    )
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    reaped = await manager.reap_expired_ephemeral_sessions()

    assert reaped == 0
    assert session.session_id in manager._sessions
    assert await store.get_session(session.session_id) is not None


@pytest.mark.asyncio
async def test_reaper_never_reaps_non_ephemeral_session():
    store = InMemorySessionStore()
    manager = SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
        ephemeral_session_ttl_seconds=1800.0,
    )
    # A kept (non-ephemeral) session, even very old, must never be reaped.
    client = PhoenixClient("ws://localhost:4000/socket")
    kept = GameSession(
        session_id="44444444-4444-4444-4444-444444444444",
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug="kept-room-1",
        created_at=datetime.now(timezone.utc) - timedelta(days=30),
        client=client,
        channel=_make_channel(),
        ephemeral=False,
    )
    kept.client.leave = AsyncMock()
    kept.client.disconnect = AsyncMock()
    await _register(manager, kept)

    reaped = await manager.reap_expired_ephemeral_sessions()

    assert reaped == 0
    kept.client.leave.assert_not_awaited()
    assert kept.session_id in manager._sessions
    assert await store.get_session(kept.session_id) is not None


@pytest.mark.asyncio
async def test_reaper_is_idempotent_against_prior_teardown():
    """A record removed by a client teardown leaves nothing for the reaper to do."""
    store = InMemorySessionStore()
    manager = SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
        ephemeral_session_ttl_seconds=1800.0,
    )
    session = _make_ephemeral_session(
        session_id="55555555-5555-5555-5555-555555555555",
        room_slug="torn-down-room",
        created_at=datetime.now(timezone.utc) - timedelta(seconds=3600),
    )
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    # Client fast-path teardown removes it first.
    await manager.delete_session(session.session_id)

    # The reaper then finds nothing to reap and does not error.
    reaped = await manager.reap_expired_ephemeral_sessions()
    assert reaped == 0


@pytest.mark.asyncio
async def test_reaper_removes_stale_store_record_not_in_pool():
    """An expired ephemeral record present only in the store is still reclaimed."""
    store = InMemorySessionStore()
    manager = SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="dev@example.com",
        password="password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
        session_store=store,
        ephemeral_session_ttl_seconds=1800.0,
    )
    created = (datetime.now(timezone.utc) - timedelta(seconds=3600)).isoformat()
    await store.put_session(
        {
            "session_id": "66666666-6666-6666-6666-666666666666",
            "plugin_name": "marvel-champions",
            "plugin_id": 1,
            "room_slug": "orphan-room",
            "created_at": created,
            "frontend_url": None,
            "ephemeral": True,
        }
    )

    reaped = await manager.reap_expired_ephemeral_sessions()

    assert reaped == 1
    assert await store.get_session("66666666-6666-6666-6666-666666666666") is None


# ---------------------------------------------------------------------------
# Ephemeral reconstruction teardown (client fast path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_ephemeral_session_closes_its_dragncards_room():
    # An ephemeral reconstruction owns its room, so the explicit teardown must
    # close the room too — otherwise every "board at this event" view leaves a
    # DragnCards room behind forever.
    store = InMemorySessionStore()
    manager = _make_manager_with_store(store)
    session = _make_ephemeral_session(
        session_id="77777777-7777-7777-7777-777777777777",
        room_slug="recon-room-1",
        created_at=datetime.now(timezone.utc),
    )
    session.channel.push = AsyncMock(return_value={})
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    await manager.delete_session(session.session_id)

    assert session.channel.push.await_args.args[0] == "close_room"
    assert session.session_id not in manager._sessions
    assert await store.get_session(session.session_id) is None
    assert await store.get_session_id_by_slug("recon-room-1") is None


@pytest.mark.asyncio
async def test_delete_non_ephemeral_session_leaves_the_room_open():
    # A kept session's room belongs to the user; deleting the session must only
    # detach this client from it.
    store = InMemorySessionStore()
    manager = _make_manager_with_store(store)
    session = _make_uuid_session()
    session.channel.push = AsyncMock(return_value={})
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    await manager.delete_session(session.session_id)

    session.channel.push.assert_not_awaited()
    session.client.leave.assert_awaited_once()
    assert await store.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_delete_ephemeral_session_survives_a_failing_room_close():
    # Room closing is best-effort: a failure must not abort the teardown, or a
    # transient DragnCards error would strand the session record too.
    store = InMemorySessionStore()
    manager = _make_manager_with_store(store)
    session = _make_ephemeral_session(
        session_id="88888888-8888-8888-8888-888888888888",
        room_slug="recon-room-2",
        created_at=datetime.now(timezone.utc),
    )
    session.close_room = AsyncMock(side_effect=SessionError("close_room rejected"))
    session.client.leave = AsyncMock()
    session.client.disconnect = AsyncMock()
    await _register(manager, session)

    await manager.delete_session(session.session_id)

    session.close_room.assert_awaited_once()
    session.client.leave.assert_awaited_once()
    session.client.disconnect.assert_awaited_once()
    assert session.session_id not in manager._sessions
    assert await store.get_session(session.session_id) is None
