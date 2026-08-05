"""Claiming seats so the game log is complete.

An unoccupied seat is not merely unnamed: Marvel Champions logs each seat's draw
through that seat's recorded alias and, guarding the line on the alias being
defined, writes nothing at all when the seat is empty. history-service records
that log and eval-service judges from it, so an unclaimed seat's moves never
reach evaluation. These tests pin the claiming behaviour and — just as
importantly — pin that claiming can fail without taking the caller down with it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from game_service.logic.exceptions import SessionError
from game_service.logic.session import GameSession
from game_service.logic.session_manager import SessionManager
from game_service.phoenix_client.client import Channel, PhoenixClient

pytestmark = pytest.mark.asyncio


def _make_session() -> GameSession:
    client = PhoenixClient("ws://localhost:4000/socket")
    return GameSession(
        session_id="test-session",
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug="test-room",
        created_at=datetime.now(timezone.utc),
        client=client,
        channel=Channel(topic="room:test", join_ref="1", client=client),
    )


def _make_manager() -> SessionManager:
    return SessionManager(
        dragncards_http_url="http://localhost:4000",
        dragncards_ws_url="ws://localhost:4000/socket",
        email="bot@example.invalid",
        password="not-a-real-password",
        plugin_registry={"marvel-champions": {"id": 1, "version": 1, "name": "MC"}},
    )


def _state(**seats: int | None) -> dict:
    return {
        "game": {
            "playerInfo": {
                seat: ({"id": uid} if uid is not None else None)
                for seat, uid in seats.items()
            }
        }
    }


# ---------------------------------------------------------------------------
# GameSession.claim_seat — pushed, then confirmed from state
# ---------------------------------------------------------------------------


async def test_claim_seat_confirms_from_room_state():
    session = _make_session()
    session.set_seat = AsyncMock()
    session._request_fresh_state = AsyncMock(return_value=_state(player2=42))

    await session.claim_seat(player_id="player2", user_id=42)

    session.set_seat.assert_awaited_once_with(player_id="player2", user_id=42)
    session._request_fresh_state.assert_awaited()


async def test_claim_seat_waits_for_a_late_broadcast():
    """Occupancy arrives by broadcast, so the first read can precede it."""
    session = _make_session()
    session.set_seat = AsyncMock()
    session._request_fresh_state = AsyncMock(
        side_effect=[_state(player2=None), _state(player2=42)]
    )

    await session.claim_seat(player_id="player2", user_id=42, poll_interval=0)

    assert session._request_fresh_state.await_count == 2


async def test_claim_seat_raises_when_the_seat_never_takes():
    """The whole point: a push that changed nothing must not read as success."""
    session = _make_session()
    session.set_seat = AsyncMock()
    session._request_fresh_state = AsyncMock(return_value=_state(player2=None))

    with pytest.raises(SessionError, match="player2"):
        await session.claim_seat(
            player_id="player2", user_id=42, timeout=0, poll_interval=0
        )


async def test_claim_seat_reports_a_room_that_will_not_answer():
    """A transport failure is a failed claim, not an unhandled fault."""
    from game_service.phoenix_client.client import PhoenixChannelError

    session = _make_session()
    session.set_seat = AsyncMock()
    session._request_fresh_state = AsyncMock(side_effect=PhoenixChannelError("gone"))

    with pytest.raises(SessionError, match="Could not confirm seat"):
        await session.claim_seat(player_id="player2", user_id=42)


async def test_claim_seat_refuses_a_non_seat_before_pushing():
    session = _make_session()
    session.set_seat = AsyncMock()

    with pytest.raises(ValueError):
        await session.claim_seat(player_id="player9", user_id=42)

    session.set_seat.assert_not_awaited()


# ---------------------------------------------------------------------------
# The seat has to reach the wire, because that is what DragnCards substitutes
# `playerNDeck` and `playerNNemesisSet` from.
# ---------------------------------------------------------------------------


async def _pushed_payload_for_deck_load(**kwargs) -> dict:
    session = _make_session()
    session.room.execute_game_action = AsyncMock()
    session.room.wait_for_state_change = AsyncMock()
    session._request_fresh_state = AsyncMock(return_value={"game": {}})
    session._emit_history_state_event = AsyncMock()

    await session.load_prebuilt_deck("Captain America (Hero)", **kwargs)

    return session.room.execute_game_action.await_args.args[0]


async def test_a_deck_load_carries_the_named_seat_to_dragncards():
    payload = await _pushed_payload_for_deck_load(player_n="player2")
    assert payload["options"]["player_ui"] == {"playerN": "player2"}


async def test_a_deck_load_without_a_seat_still_loads_into_the_first():
    payload = await _pushed_payload_for_deck_load()
    assert payload["options"]["player_ui"] == {"playerN": "player1"}


async def test_a_deck_load_refuses_a_non_seat():
    with pytest.raises(ValueError):
        await _pushed_payload_for_deck_load(player_n="shared")


# ---------------------------------------------------------------------------
# SessionManager.claim_seats — occupancy follows the player count
# ---------------------------------------------------------------------------


async def test_claim_seats_claims_the_seat_a_two_player_game_adds():
    manager = _make_manager()
    manager._own_user_id = AsyncMock(return_value=42)
    session = _make_session()
    session.get_state = AsyncMock(return_value=_state(player1=42, player2=None))
    session.claim_seat = AsyncMock()

    claimed = await manager.claim_seats(session, num_players=2)

    assert claimed == ["player2"]
    session.claim_seat.assert_awaited_once_with(player_id="player2", user_id=42)


async def test_claim_seats_leaves_a_seat_held_by_someone_else():
    manager = _make_manager()
    manager._own_user_id = AsyncMock(return_value=42)
    session = _make_session()
    session.get_state = AsyncMock(return_value=_state(player1=42, player2=99))
    session.claim_seat = AsyncMock()

    claimed = await manager.claim_seats(session, num_players=2)

    assert claimed == []
    session.claim_seat.assert_not_awaited()


async def test_a_failed_claim_does_not_propagate():
    """A missing log alias must never block setting a game up."""
    manager = _make_manager()
    manager._own_user_id = AsyncMock(return_value=42)
    session = _make_session()
    session.get_state = AsyncMock(
        return_value=_state(player1=42, player2=None, player3=None)
    )
    session.claim_seat = AsyncMock(side_effect=[SessionError("nope"), None])

    claimed = await manager.claim_seats(session, num_players=3)

    assert claimed == ["player3"]


async def test_claim_seats_gives_up_quietly_when_state_is_unreadable():
    manager = _make_manager()
    session = _make_session()
    session.get_state = AsyncMock(side_effect=SessionError("no state"))
    session.claim_seat = AsyncMock()

    assert await manager.claim_seats(session, num_players=2) == []
    session.claim_seat.assert_not_awaited()


async def test_claim_seats_gives_up_when_its_own_identity_is_unknown():
    """Seating an unknown id would put a stranger in the room's seats."""
    manager = _make_manager()
    manager._own_user_id = AsyncMock(return_value=None)
    session = _make_session()
    session.get_state = AsyncMock(return_value=_state(player1=None))
    session.claim_seat = AsyncMock()

    assert await manager.claim_seats(session, num_players=2) == []
    session.claim_seat.assert_not_awaited()


async def test_own_user_id_is_asked_of_dragncards_not_inferred_from_the_room():
    """A human may hold the only occupied seat; claiming for them would be wrong."""
    manager = _make_manager()
    session = _make_session()
    session.get_state = AsyncMock(return_value=_state(player1=99, player2=None))
    session.claim_seat = AsyncMock()

    async def fail(*args, **kwargs):
        raise RuntimeError("no DragnCards here")

    import game_service.logic.session_manager as sm

    original = sm.get_auth_token
    sm.get_auth_token = fail
    try:
        claimed = await manager.claim_seats(session, num_players=2)
    finally:
        sm.get_auth_token = original

    # 99 is the human in player1; it must not have been reused as our identity.
    assert claimed == []
    session.claim_seat.assert_not_awaited()
