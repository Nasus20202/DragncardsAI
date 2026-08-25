"""DragnCards player seats.

A seat in DragnCards is a *slot*, not an identity. A room's seats are the keys
``player1``..``player4`` of one map held in that room's server process, and the
seat an action acts as is taken verbatim from the action's own payload
(``options.player_ui.playerN``), never from the identity of the connection that
sent it. One authenticated connection can therefore act as every seat, which is
why this service drives multi-player games from a single DragnCards account.

What the seat map *does* decide is naming. Plugin automation reads a seat's alias
out of it, and where a log line is guarded on that alias being defined, an
unoccupied seat produces no line at all — so an unoccupied seat's moves can be
missing from the recorded game rather than merely anonymous. Keeping the map
populated for every seat in play is what this module exists to support.

The room state exposes occupancy in two shapes. ``playerInfo`` is authoritative
and keys each seat to ``{"id": <user id>, "alias": ...}``. ``playerData`` is the
older shape, carries the same fact under ``user_id``, and is read only as a
fallback so that a state predating ``playerInfo`` is still understood.
"""

from __future__ import annotations

from typing import Any

# The four seats DragnCards models. Ordered, because "the seats up to a player
# count" is a prefix of this tuple and callers rely on that ordering.
SEAT_IDS: tuple[str, ...] = ("player1", "player2", "player3", "player4")

MAX_SEATS = len(SEAT_IDS)


def normalise_seat_id(value: Any) -> str:
    """Return ``value`` as a DragnCards seat id, or raise ``ValueError``.

    Deliberately strict. A numeric index is *not* accepted: DragnCards uses this
    value directly as a key of the room's seat map, so a number writes an entry
    that no seat lookup will ever find, and it does so silently.
    """
    if not isinstance(value, str):
        raise ValueError(
            f"Invalid seat {value!r}: a seat is named {SEAT_IDS[0]}..{SEAT_IDS[-1]}, "
            "not a numeric index"
        )
    if value not in SEAT_IDS:
        raise ValueError(f"Invalid seat {value!r}: expected one of {list(SEAT_IDS)}")
    return value


def require_contiguous_seat_roster(values: Any) -> tuple[str, ...]:
    """Return an exact ``player1``..``playerN`` roster or reject it.

    Marvel's engine receives hero documents positionally, so accepting a reverse
    or gapped seat list would make the requested seat metadata disagree with the
    engine's player order.  Keep the invariant at the neutral seam rather than
    repairing it independently in each transport adapter.
    """
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("hero-deck roster must contain at least player1")
    roster = tuple(normalise_seat_id(value) for value in values)
    expected = SEAT_IDS[: len(roster)]
    if roster != expected:
        expected_text = ", ".join(expected)
        actual_text = ", ".join(roster)
        raise ValueError(
            f"hero-deck roster must be the ordered contiguous prefix "
            f"{expected_text}; received {actual_text}"
        )
    return roster


def _game_of(state: Any) -> dict[str, Any] | None:
    """The ``game`` sub-document of a room state, tolerating either nesting.

    Room state arrives as ``{"game": {...}, ...}``, but some seat facts live at
    the top level of the envelope rather than inside ``game``, so both are tried
    by the readers below.
    """
    if not isinstance(state, dict):
        return None
    game = state.get("game")
    return game if isinstance(game, dict) else None


def seat_occupants(state: Any) -> dict[str, int | None]:
    """Map every seat to the user id holding it, or ``None`` when vacant.

    Seats absent from the room state are reported vacant rather than omitted, so
    a caller can iterate the result without also knowing which shape the state
    happened to use.
    """
    occupants: dict[str, int | None] = {seat: None for seat in SEAT_IDS}

    game = _game_of(state)
    containers: list[Any] = []
    for source in (state, game):
        if not isinstance(source, dict):
            continue
        containers.append(source.get("playerInfo"))
    for source in (state, game):
        if not isinstance(source, dict):
            continue
        containers.append(source.get("playerData"))

    for container in containers:
        if not isinstance(container, dict):
            continue
        for seat in SEAT_IDS:
            if occupants[seat] is not None:
                continue
            info = container.get(seat)
            if not isinstance(info, dict):
                continue
            # ``playerInfo`` says ``id``; the older ``playerData`` says ``user_id``.
            user_id = info.get("id")
            if user_id is None:
                user_id = info.get("user_id")
            if isinstance(user_id, int):
                occupants[seat] = user_id

    return occupants


def seats_in_play(num_players: int) -> list[str]:
    """The seats a room with ``num_players`` players uses.

    Clamped to the four seats DragnCards models: a plugin may accept a larger
    player count than DragnCards has seats for, and asking to claim a fifth seat
    would fail rather than being ignored.
    """
    if num_players < 1:
        return []
    return list(SEAT_IDS[: min(num_players, MAX_SEATS)])


def seats_to_claim(state: Any, num_players: int) -> list[str]:
    """The vacant seats within ``num_players``.

    An occupied seat is skipped whoever holds it. If it is us, nothing needs
    doing; if it is somebody else, they are a participant this service did not
    put there and evicting them is not this service's call.
    """
    occupants = seat_occupants(state)
    return [seat for seat in seats_in_play(num_players) if occupants.get(seat) is None]


def seat_held_by(state: Any, seat_id: str, user_id: int) -> bool:
    """Whether ``seat_id`` currently holds ``user_id`` in ``state``."""
    return seat_occupants(state).get(seat_id) == user_id
