from __future__ import annotations

import re

from eval_service.schemas.history import StoredEvent

# Canonical single-player id used when a game has one player (or when the
# player count cannot be derived from recorded state).
DEFAULT_PLAYER = "player1"

_PLAYER_KEY_RE = re.compile(r"^player\d+$")


def _game_state(event: StoredEvent) -> dict | None:
    """Return the DragnCards state dict for a ``game-service`` state event.

    Recorded state comes in two shapes: the raw DragnCards state nests the
    interesting fields under ``payload.state.game`` and the simplified state
    exposes them flat under ``payload.state``. Both are tolerated so attribution
    is robust to which representation was recorded.
    """
    if event.actor != "game-service":
        return None
    state = event.payload.get("state")
    if not isinstance(state, dict):
        return None
    game = state.get("game")
    if isinstance(game, dict) and game:
        return game
    return state


def _num_players(game: dict) -> int:
    """Best-effort player count from a state dict.

    Prefers an explicit ``numPlayers``; otherwise counts the ``playerData`` /
    ``players`` keys that look like ``player1``..``playerN`` (ignoring seats with
    no joined player). Returns ``0`` when nothing is derivable.
    """
    raw = game.get("numPlayers")
    if isinstance(raw, int) and raw > 0:
        return raw
    for key in ("playerData", "players"):
        data = game.get(key)
        if isinstance(data, dict) and data:
            seats = [k for k in data if isinstance(k, str) and _PLAYER_KEY_RE.match(k)]
            if seats:
                return len(seats)
    return 0


def _player_seats(game: dict) -> list[str]:
    """The ordered ``player1``..``playerN`` seat ids present in the state."""
    n = _num_players(game)
    if n > 0:
        return [f"player{i}" for i in range(1, n + 1)]
    return [DEFAULT_PLAYER]


def _first_player(game: dict) -> str | None:
    """The active first player id (``player1``..) if recorded."""
    raw = game.get("firstPlayer")
    if isinstance(raw, str) and _PLAYER_KEY_RE.match(raw):
        return raw
    if isinstance(raw, int) and raw >= 1:
        return f"player{raw}"
    return None


def _nearest_state_game(events: list[StoredEvent], target_seq: int) -> dict | None:
    """The state dict at-or-before ``target_seq`` (else the nearest after)."""
    states = [(e.seq, _game_state(e)) for e in events if e.actor == "game-service"]
    states = [(seq, g) for seq, g in states if g is not None]
    if not states:
        return None
    before = [(seq, g) for seq, g in states if seq <= target_seq]
    if before:
        return max(before, key=lambda item: item[0])[1]
    return min(states, key=lambda item: item[0])[1]


def _recorded_player(event: StoredEvent) -> str | None:
    """The acting seat recorded on the move itself, if the producer knew it.

    An orchestrated multi-player game runs one agent per seat, so the producer
    knows exactly who acted and stamps it on the payload. That is ground truth
    and outranks anything inferred from board state.
    """
    value = event.payload.get("player")
    if isinstance(value, str) and _PLAYER_KEY_RE.match(value):
        return value
    return None


def _explicit_player_hint(event: StoredEvent) -> str | None:
    """A player id explicitly carried on an agent move's arguments, if any.

    Some recorded actions carry the acting player directly (``player_n`` /
    ``player``); when present it is the most reliable attribution signal
    available for a move the producer did not stamp.
    """
    args = event.payload.get("arguments")
    if not isinstance(args, dict):
        return None
    for key in ("player_n", "player", "playerN"):
        value = args.get(key)
        if isinstance(value, str) and _PLAYER_KEY_RE.match(value):
            return value
    return None


def attribute_move(events: list[StoredEvent], target_seq: int) -> str:
    """Attribute an agent move to the player who was active for it.

    A seat recorded on the move itself always wins — including when the player
    count cannot be derived from state, since a failure to infer must never
    override a fact. Otherwise: single-player games (or games whose player count
    cannot be derived) attribute to ``player1``, and multi-player games take the
    acting player from an explicit hint on the move's arguments when present,
    else from the game state's ``firstPlayer`` rotation — agent moves within a
    round are dealt out in turn order starting at the first player, so the k-th
    agent move of a round maps to the k-th seat in that rotation.
    """
    target = next((e for e in events if e.seq == target_seq), None)
    if target is not None:
        recorded = _recorded_player(target)
        if recorded is not None:
            return recorded

    game = _nearest_state_game(events, target_seq)
    seats = _player_seats(game) if game else [DEFAULT_PLAYER]
    if len(seats) <= 1:
        return DEFAULT_PLAYER

    if target is not None:
        hint = _explicit_player_hint(target)
        if hint is not None and hint in seats:
            return hint

    first = _first_player(game) if game else None
    rotation = _rotate_seats(seats, first)

    # Position of this move within its round's agent-move sequence determines
    # the seat: turn order proceeds first-player-first through the rotation.
    index = _move_index_in_round(events, target_seq)
    return rotation[index % len(rotation)]


def _rotate_seats(seats: list[str], first: str | None) -> list[str]:
    if first is None or first not in seats:
        return list(seats)
    start = seats.index(first)
    return seats[start:] + seats[:start]


def _round_bounds(events: list[StoredEvent], target_seq: int) -> tuple[int, int]:
    """The ``(from_seq, to_seq)`` of the round containing ``target_seq``.

    Imported lazily to avoid a circular import with ``judge.assembly``. Falls
    back to the whole timeline when no round boundary contains the move.
    """
    from eval_service.judge.assembly import detect_round_boundaries

    for _rn, frm, to in detect_round_boundaries(events):
        if frm <= target_seq <= to:
            return frm, to
    ordered = sorted(e.seq for e in events)
    return (ordered[0], ordered[-1]) if ordered else (target_seq, target_seq)


def _move_index_in_round(events: list[StoredEvent], target_seq: int) -> int:
    frm, to = _round_bounds(events, target_seq)
    agent_seqs = sorted(
        e.seq for e in events if e.actor == "agent" and frm <= e.seq <= to
    )
    try:
        return agent_seqs.index(target_seq)
    except ValueError:
        return 0


def players_in_span(events: list[StoredEvent], from_seq: int, to_seq: int) -> list[str]:
    """The ordered set of players who acted (made an agent move) in a span.

    Single-player games collapse to ``[player1]``. The result is ordered by
    seat id so per-player target expansion is deterministic.
    """
    acted: set[str] = set()
    for event in events:
        if event.actor == "agent" and from_seq <= event.seq <= to_seq:
            acted.add(attribute_move(events, event.seq))
    if not acted:
        return [DEFAULT_PLAYER]
    return sorted(acted, key=_seat_sort_key)


def _seat_sort_key(player: str) -> tuple[int, str]:
    match = re.match(r"^player(\d+)$", player)
    if match:
        return (int(match.group(1)), player)
    return (10_000, player)
