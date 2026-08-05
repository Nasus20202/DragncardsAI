"""Seat identity is read from session metadata, and only orchestrated seats have one.

Everything gated on "is this job a seat?" — the seat guard, the player-to-player
channel, the illegal-action findings a seat is handed — resolves through
:func:`resolve_seat_identity`. These tests pin the two directions that matter:

* A seat of an orchestrated session resolves to its own seat id and its
  orchestrating session, taken from ``metadata_json`` and nowhere else.
* Everything that is *not* such a seat resolves to ``None``. The case worth
  singling out is a player child of a ``chat`` session: chat mode tags that child
  with a ``player_id`` too, so the tag on its own must never be read as seat
  identity — if it were, the chat flow (the one actually in use) would silently
  acquire seat scoping.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
    resolve_seat_identity,
    session_orchestrator_session_id,
)
from agent_orchestrator.runtime.session_modes import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
)


class _Session:
    """The two attributes seat resolution reads, and nothing else."""

    def __init__(self, session_id: str, metadata: dict[str, Any], mode: str) -> None:
        self.id = session_id
        self.metadata_json = metadata
        self.session_mode = mode


def _loader(*sessions: _Session):
    by_id = {session.id: session for session in sessions}

    async def load_session(session_id: str) -> _Session | None:
        return by_id.get(session_id)

    return load_session


def _seat(orchestrator_id: str = "table", player_id: str = "player1") -> _Session:
    return _Session(
        "seat-session",
        {
            SESSION_PLAYER_ID_KEY: player_id,
            SESSION_ORCHESTRATOR_ID_KEY: orchestrator_id,
        },
        SESSION_MODE_CHAT,
    )


async def test_an_orchestrated_seat_resolves_to_its_own_seat() -> None:
    table = _Session("table", {}, SESSION_MODE_ORCHESTRATED)
    seat = _seat()

    identity = await resolve_seat_identity(seat, load_session=_loader(table, seat))

    assert identity is not None
    assert identity.player_id == "player1"
    assert identity.orchestrator_session_id == "table"


async def test_the_orchestrating_job_holds_no_seat() -> None:
    table = _Session("table", {}, SESSION_MODE_ORCHESTRATED)

    assert await resolve_seat_identity(table, load_session=_loader(table)) is None


async def test_a_chat_sessions_player_child_holds_no_seat() -> None:
    """The regression this whole helper exists to prevent.

    ``prompt_player_agent`` tags its child with ``player_id`` in chat mode as well,
    so a check for that tag alone would apply seat scoping to the pre-orchestration
    flow. The orchestrating session's mode is what decides.
    """
    table = _Session("table", {}, SESSION_MODE_CHAT)
    seat = _seat()

    assert await resolve_seat_identity(seat, load_session=_loader(table, seat)) is None


async def test_a_plain_chat_session_holds_no_seat() -> None:
    session = _Session("solo", {}, SESSION_MODE_CHAT)

    assert await resolve_seat_identity(session, load_session=_loader(session)) is None


async def test_a_seat_pointing_at_a_missing_orchestrator_holds_no_seat() -> None:
    """Fail closed on identity, open on behaviour.

    A seat whose orchestrating session cannot be read has no established mode, so
    it is treated as holding no seat. That is the conservative answer for the chat
    flow's sake: the alternative — assuming orchestrated — would start scoping a
    session nobody confirmed was a game.
    """
    seat = _seat(orchestrator_id="vanished")

    assert await resolve_seat_identity(seat, load_session=_loader(seat)) is None


async def test_a_seat_with_no_orchestrator_recorded_holds_no_seat() -> None:
    seat = _Session(
        "seat-session", {SESSION_PLAYER_ID_KEY: "player1"}, SESSION_MODE_CHAT
    )

    assert await resolve_seat_identity(seat, load_session=_loader(seat)) is None


@pytest.mark.parametrize(
    "player_id",
    ["player0", "player5", "PLAYER1", "player", "player1 ", "", "player11"],
)
async def test_a_metadata_seat_id_that_is_not_a_seat_holds_no_seat(
    player_id: str,
) -> None:
    """Seat ids are `player1`..`player4`; anything else is not a seat at all."""
    table = _Session("table", {}, SESSION_MODE_ORCHESTRATED)
    seat = _Session(
        "seat-session",
        {
            SESSION_PLAYER_ID_KEY: player_id,
            SESSION_ORCHESTRATOR_ID_KEY: "table",
        },
        SESSION_MODE_CHAT,
    )

    assert await resolve_seat_identity(seat, load_session=_loader(table, seat)) is None


async def test_the_orchestrator_id_is_read_only_from_metadata() -> None:
    assert session_orchestrator_session_id(_seat()) == "table"
    assert session_orchestrator_session_id(_Session("x", {}, SESSION_MODE_CHAT)) is None
