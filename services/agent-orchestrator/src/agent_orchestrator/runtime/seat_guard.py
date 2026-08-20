"""Server-side scoping of a player seat's tool calls to its own cards.

In orchestrated mode each Marvel Champions seat is played by its own agent, and
"act only on your own hero" used to be a sentence in a skill file. A sentence is
not enforcement: an agent that is confused, or led there by a card name or a
message from another seat, ignores it and nothing stops the call. This module is
the replacement — a pure check run on every tool call a seat makes, before the
tool is dispatched, refusing any call whose arguments name a seat other than the
caller's own.

The caller's seat is *never* taken from the arguments. It arrives as
:class:`~agent_orchestrator.runtime.player_agents.SeatIdentity`, resolved from the
child session's ``metadata_json`` which the orchestrator wrote at seat-session
creation and which no tool a player holds can write. A seat that writes
``player_id: "player2"``, or prose claiming to be another seat, therefore changes
only *what it is asking for* — never *who is asking*, which is the whole point.

## What this guard covers

DragnCards addresses seat ownership in exactly three shapes, and each is checked:

1. **A bare seat identifier.** A string that is precisely one of
   ``player1``..``player4`` — the form game-service takes as ``player_n``.
2. **A player-owned group id.** DragnCards' own ``player<N><Group>`` naming:
   ``player2Hand``, ``player3Play``, ``player1Discard``. The digit is the owning
   seat, so a group whose digit is not the caller's is a foreign group.
3. **An explicit player-identifying argument.** An argument whose *name* says it
   carries a player (``player_id``, ``playerId``, ``player``, ``player_index``,
   ``playerIndex``, ``player_n``) and whose value is a seat id, or an integer or
   numeric string 1-4 that indexes one.

Shapes 1 and 2 are checked **both as mapping values and as mapping keys**. A key
names a seat exactly as a value does — ``{"updates": {"player2Hand": [...]}}``
means "do this to player 2", and the key is the only place it says so — so a
deny-list that read only values would be blind to half of every mapping. No
game-service tool currently takes a group-keyed mapping as input (the one
group-keyed shape, ``GuiUpdateResponse.updates``, is a *response*), so this is
hardening rather than a closed hole; it is here because the day someone adds a
batched group-keyed tool is exactly the day nobody re-reads this module. Shape 3's
numeric-index reading is *not* applied to keys: it exists to interpret a value
whose argument name declares it a player, and a key of ``"2"`` declares nothing,
so reading it as a seat would only manufacture false refusals.

Nested ``dict`` and ``list`` values are walked too, so a foreign group buried in a
batched payload is caught and reported by its path (``updates[0].groupId``).

## What this guard does not cover, stated plainly

- **It is a deny-list over recognised seat-shaped values, not a whole-game
  authorization model.** It catches the realistic cases because those are how
  ownership is addressed. A tool that identified ownership by an opaque card id
  would slip through — nothing in ``{"card_id": "e3f1a…"}`` reveals whose card it
  is without reading game state, which this function deliberately does not do.
  The mitigation is that such an id is meaningless to a seat that has only ever
  seen its own state; the guarantee is not that every foreign action is
  impossible, only that every *addressable* one is refused.
- **Groups no seat owns are unrestricted, on purpose.** A seat legitimately reads
  and affects the villain and shared areas during its own turn — attacking the
  villain, thwarting the main scheme, taking an encounter card — so refusing
  ``sharedMainScheme`` or ``villainDiscard`` would break legal play rather than
  protect anything. Ownership is what is scoped here; nothing else is.
- **It does not police turn or phase authority.** *When* an action happens — that
  a seat must not advance the phase or play out of turn — is an orchestrator-side
  judgement made from game state, not a property of the arguments. This function
  answers only "whose cards does this call touch". That judgement now lives in
  :mod:`agent_orchestrator.runtime.seat_turn_guard`: after this guard has passed,
  the call site reads the current step from game state and records a DRA-30
  illegal-action finding when a seat advances the phase or acts outside the
  player phase. The seat guard answers *whose*, the turn guard answers *when*,
  and the two modules read as one story.
- **Traversal is bounded.** Past :data:`MAX_TRAVERSAL_DEPTH` levels of nesting or
  :data:`MAX_TRAVERSAL_NODES` visited nodes, values are simply not examined, so a
  pathological payload cannot make the guard cost more than the tool call it
  guards. A foreign seat named only below those bounds is not caught.
- **Only ``str`` and ``int`` scalars are examined.** A seat encoded as a float, or
  inside a base64 blob, or spelled in prose, is not a value this recognises.

The function is pure: no repository, no I/O, no logging. That is what makes the
whole rule directly testable, and it is why the durable ``seat_scope_violation``
event and the refusal result are the caller's job rather than this module's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from agent_orchestrator.runtime.platforms import (
    DEFAULT_PLATFORM,
    PLATFORM_DRAGNCARDS,
    normalize_platform,
)

# The seat a value names, when the value is nothing but a seat id. Case-insensitive
# on purpose: the guard is a deny-list, so `PLAYER2` must not be a way around it.
SEAT_ID_PATTERN = re.compile(r"^player([1-4])$", re.IGNORECASE)

# DragnCards' player-owned group naming: `player` + the owning seat's digit + a
# group name. The suffix must start with a letter, which is what keeps `player10`
# — an id that names no seat at all — from reading as seat 1's group `0`.
PLAYER_GROUP_PATTERN = re.compile(
    r"^player([1-4])([A-Za-z][A-Za-z0-9_]*)$", re.IGNORECASE
)

# Argument names that carry a player. Compared after lowercasing and dropping
# underscores, so `player_id`, `playerId`, `player_n`, `playerN`, `player_index`
# and `playerIndex` all collapse onto one of these.
PLAYER_ARGUMENT_NAMES = frozenset({"player", "playerid", "playerindex", "playern"})

# Traversal bounds. Deep or wide payloads are real (a batched update carries a list
# of dicts), but the guard runs on every tool call of every seat, so it refuses to
# be the expensive part of one. Anything past these bounds goes unchecked.
MAX_TRAVERSAL_DEPTH = 12
MAX_TRAVERSAL_NODES = 2048

# A group name has no length limit in the pattern above — narrowing it would turn
# an absurdly long value into an *allowed* one, which is the wrong way to be
# strict. The value is instead truncated where it is reported, so an oversized
# argument cannot be echoed back into the model's context, the durable event, and
# the dashboard at full length.
MAX_REPORTED_VALUE_LENGTH = 120


@dataclass(frozen=True)
class SeatScopeViolation:
    """A tool call that named a seat other than the caller's own.

    ``argument`` is the path where the foreign seat was found, so a refusal points
    at one place in the payload rather than at the payload. ``value`` is the
    offending value exactly as the model wrote it, which is what makes the message
    correctable instead of merely negative.
    """

    caller_player_id: str
    foreign_player_id: str
    tool_name: str
    argument: str
    value: str

    @property
    def message(self) -> str:
        """The refusal the model reads, written so it can fix the call itself."""
        return (
            f"Refused: the argument `{self.argument}` of `{self.tool_name}` names "
            f"seat {self.foreign_player_id} (value `{self.value}`), but you play "
            f"seat {self.caller_player_id}. A seat may act only with its own "
            f"cards, and this is enforced by the server, so no instruction, "
            f"explanation, or claim of permission will change it. Reissue the call "
            f"using {self.caller_player_id}'s own seat id and groups, or a shared "
            f"or villain group that no seat owns. If another seat needs to act, "
            f"report that to the orchestrator instead of acting for it."
        )


def check_seat_scope(
    *,
    caller_player_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    platform: str = DEFAULT_PLATFORM,
    game_state: Mapping[str, Any] | None = None,
) -> SeatScopeViolation | None:
    """The first foreign seat named in ``arguments``, or ``None`` if there is none.

    ``caller_player_id`` is the seat the *server* says is calling. Traversal is
    depth-first in insertion order and returns on the first violation, so the same
    call always produces the same message — a refusal that named a different
    argument each time would be impossible to act on.
    """
    if not isinstance(arguments, dict):
        return None
    platform = normalize_platform(platform)
    budget = _Budget()
    return _walk(
        node=arguments,
        path="",
        key=None,
        depth=0,
        budget=budget,
        caller_player_id=caller_player_id,
        tool_name=tool_name,
        platform=platform,
        card_owners=_card_owners(game_state) if platform != PLATFORM_DRAGNCARDS else {},
    )


class _Budget:
    """The shared node count for one traversal, exhausted rather than reset."""

    def __init__(self) -> None:
        self.remaining = MAX_TRAVERSAL_NODES

    def spend(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


def _walk(
    *,
    node: Any,
    path: str,
    key: str | None,
    depth: int,
    budget: _Budget,
    caller_player_id: str,
    tool_name: str,
    platform: str = DEFAULT_PLATFORM,
    card_owners: dict[str, str] | None = None,
    target_context: bool = False,
) -> SeatScopeViolation | None:
    if depth > MAX_TRAVERSAL_DEPTH or not budget.spend():
        return None
    if isinstance(node, dict):
        for child_key, child in node.items():
            if not isinstance(child_key, str):
                continue
            child_path = child_key if not path else f"{path}.{child_key}"
            # A mapping names a seat in its KEY as readily as in a value:
            # `{"updates": {"player2Hand": [...]}}` says "do this to player 2",
            # and the key is the only place it says so. Checked before descending,
            # so the refusal names the key rather than something inside the value
            # it guards, and so first-violation-wins ordering stays depth-first.
            foreign_key = _foreign_seat_in_text(
                child_key,
                caller_player_id,
                allow_group_ids=platform == PLATFORM_DRAGNCARDS,
            )
            if foreign_key is not None:
                return SeatScopeViolation(
                    caller_player_id=caller_player_id,
                    foreign_player_id=foreign_key,
                    tool_name=tool_name,
                    argument=child_path,
                    value=_reported_value(child_key),
                )
            violation = _walk(
                node=child,
                path=child_path,
                key=child_key,
                depth=depth + 1,
                budget=budget,
                caller_player_id=caller_player_id,
                tool_name=tool_name,
                platform=platform,
                card_owners=card_owners,
                target_context=target_context or _is_target_argument(child_key),
            )
            if violation is not None:
                return violation
        return None
    if isinstance(node, list):
        for index, child in enumerate(node):
            violation = _walk(
                node=child,
                path=f"{path}[{index}]",
                # The list's own name still identifies the player for an entry
                # like `player_ids: ["player2"]`, so the key travels down.
                key=key,
                depth=depth + 1,
                budget=budget,
                caller_player_id=caller_player_id,
                tool_name=tool_name,
                platform=platform,
                card_owners=card_owners,
                target_context=target_context,
            )
            if violation is not None:
                return violation
        return None
    foreign = _foreign_seat(
        key=key,
        value=node,
        caller_player_id=caller_player_id,
        allow_group_ids=platform == PLATFORM_DRAGNCARDS,
    )
    if foreign is None and target_context and card_owners:
        foreign = _foreign_card_owner(
            key=key,
            value=node,
            caller_player_id=caller_player_id,
            card_owners=card_owners,
        )
    if foreign is None:
        return None
    return SeatScopeViolation(
        caller_player_id=caller_player_id,
        foreign_player_id=foreign,
        tool_name=tool_name,
        argument=path or "arguments",
        value=_reported_value(node),
    )


def _reported_value(value: Any) -> str:
    text = str(value)
    if len(text) <= MAX_REPORTED_VALUE_LENGTH:
        return text
    return f"{text[:MAX_REPORTED_VALUE_LENGTH]}…"


def _foreign_seat(
    *,
    key: str | None,
    value: Any,
    caller_player_id: str,
    allow_group_ids: bool = True,
) -> str | None:
    """The seat this scalar names, when that seat is not the caller's.

    ``bool`` is excluded before the integer check because it is an ``int`` in
    Python, and ``True`` would otherwise read as seat 1 under a name like
    ``player``.
    """
    named = _named_seat(key=key, value=value, allow_group_ids=allow_group_ids)
    if named is None or named == _canonical_seat(caller_player_id):
        return None
    return named


def _foreign_seat_in_text(
    text: str, caller_player_id: str, *, allow_group_ids: bool = True
) -> str | None:
    """The foreign seat a bare string names, by seat id or owned-group id.

    Used for mapping keys. Deliberately narrower than :func:`_foreign_seat`: it
    does not apply the numeric-index reading, because that reading exists to
    interpret a value whose *argument name* declares it to be a player, and a key
    has no such name — it *is* the name. Reading a key of ``"2"`` as seat 2 would
    make every ordinary integer-keyed mapping a refusal, which widens the
    deny-list into false positives rather than closing a hole.
    """
    named = _seat_from_string(text, allow_group_ids=allow_group_ids)
    if named is None or named == _canonical_seat(caller_player_id):
        return None
    return named


def _named_seat(
    *, key: str | None, value: Any, allow_group_ids: bool = True
) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        seat = _seat_from_string(value, allow_group_ids=allow_group_ids)
        if seat is not None:
            return seat
        return _seat_from_index(value) if _is_player_argument(key) else None
    if isinstance(value, int):
        return _seat_from_index(value) if _is_player_argument(key) else None
    return None


def _seat_from_string(value: str, *, allow_group_ids: bool = True) -> str | None:
    """The seat a string value names, by seat id or by owned-group id."""
    text = value.strip()
    match = SEAT_ID_PATTERN.match(text)
    if match is None and allow_group_ids:
        match = PLAYER_GROUP_PATTERN.match(text)
    return f"player{match.group(1)}" if match is not None else None


def _seat_from_index(value: Any) -> str | None:
    """The seat an index names, for a value under a player-identifying name."""
    text = str(value).strip()
    return f"player{text}" if text in {"1", "2", "3", "4"} else None


def _is_player_argument(key: str | None) -> bool:
    if key is None:
        return False
    return key.lower().replace("_", "") in PLAYER_ARGUMENT_NAMES


def _canonical_seat(player_id: str) -> str:
    return player_id.strip().lower()


_TARGET_ARGUMENT_NAMES = frozenset(
    {
        "target",
        "targets",
        "targetid",
        "targetids",
        "targetcard",
        "targetcards",
        "cardid",
        "cardids",
        "instanceid",
        "instanceids",
        "card_id",
        "card_ids",
        "instance_id",
        "instance_ids",
    }
)
_CARD_ID_KEYS = frozenset(
    {
        "id",
        "cardid",
        "instanceid",
        "card_id",
        "instance_id",
    }
)


def _is_target_argument(key: str) -> bool:
    return key.lower() in _TARGET_ARGUMENT_NAMES


def _foreign_card_owner(
    *,
    key: str | None,
    value: Any,
    caller_player_id: str,
    card_owners: dict[str, str],
) -> str | None:
    """Resolve a marvel-lcg card id through normalised zone ownership."""

    key_name = key.lower() if key is not None else ""
    if key_name not in _CARD_ID_KEYS and key_name not in {
        "target",
        "targets",
        "targetid",
        "targetids",
    }:
        return None
    owner = card_owners.get(str(value))
    if owner is None or owner == _canonical_seat(caller_player_id):
        return None
    return owner


def _card_owners(game_state: Mapping[str, Any] | None) -> dict[str, str]:
    """Build a card-id-to-seat map from the neutral zone projection.

    The map is intentionally derived from the normalised state, not from a
    marvel-lcg object-id spelling. Shared and unattributed zones are omitted,
    which leaves those targets available to the caller as the neutral contract
    requires.
    """

    if not isinstance(game_state, Mapping):
        return {}
    zones = game_state.get("zones")
    if not isinstance(zones, Mapping):
        return {}
    owners: dict[str, str] = {}
    for zone_name, cards in zones.items():
        if not isinstance(zone_name, str):
            continue
        match = re.match(r"^player([1-4])(?:[A-Z].*)?$", zone_name)
        if match is None or not isinstance(cards, list):
            continue
        owner = f"player{match.group(1)}"
        for card in cards:
            if not isinstance(card, Mapping):
                continue
            for key in ("id", "instanceId", "cardId", "instance_id"):
                card_id = card.get(key)
                if card_id is not None:
                    owners[str(card_id)] = owner
    return owners
