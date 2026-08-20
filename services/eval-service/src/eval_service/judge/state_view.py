"""Project a recorded DragnCards state down to what a judge needs to rule.

``game-service`` records the RAW DragnCards room state on every ``game_state``
event. Measured on real recorded games that payload is ~450-470 KB, of which
~225 KB is ``deltas`` (DragnCards' internal undo/replay log) and most of the rest
is plugin configuration: layouts, automation action lists, rule definitions,
image URLs, and both faces of every card definition including artwork geometry.

Serialising that and clipping it to a character budget is the worst of both
worlds. ``deltas`` sorts before ``game`` under canonical (sorted-key) JSON, so a
20,000-character prefix of a 470,000-character state is *entirely* delta log: the
judge was paying ~13,700 prompt tokens per move to see no board at all.

This module builds a small structured projection instead, mirroring the
`SimplifiedGameState` shape the game-service already serves to the playing agent
(``roundNumber``, ``mode``, ``stepId``, per-player hit points / hand size, and
per-zone card lists). The judge therefore sees the same view of the table the
agent saw when it decided, which is the right basis for grading that decision.

Hidden information stays hidden: face-down cards and cards showing a generic
``player``/``encounter`` back collapse to a ``HIDDEN`` entry with a count, so deck
contents never leak into a prompt whose rubric says not to assume hidden
information (and 60+ deck cards stop being serialised).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from eval_service.schemas.history import (
    PLATFORM_DRAGNCARDS,
    PLATFORM_MARVEL_LCG,
    Platform,
)

logger = logging.getLogger(__name__)

# Human-readable step descriptions, mirroring the game-service's own mapping so
# the judge reads the same phase vocabulary the playing agent was given.
STEP_DESCRIPTIONS: dict[str, str] = {
    "0.0": "Beginning of Round",
    "0.1": "End of Round",
    "1.1": "Player Turn",
    "1.2": "End of Player Phase",
    "2.1": "Place threat on the main scheme.",
    "2.2": "The villain activates once per player, along with any eligible minions",
    "2.3": "Deal one encounter card to each player.",
    "2.4": "Reveal encounter cards.",
    "2.5": "Pass the first player token and end the round.",
}

# Card backs DragnCards uses for a face-down card; never a real card name.
_GENERIC_BACKS = ("player", "encounter")

# Top-level game fields worth carrying: scalar context a judge reasons about.
_GAME_SCALARS = (
    "roundNumber",
    "mode",
    "stepId",
    "firstPlayer",
    "numPlayers",
    "villainHitPoints",
)


def canonical_json(value: Any) -> str:
    """Serialize deterministically, falling back to ``repr`` on odd types."""
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError, ValueError:
        return repr(value)


def is_raw_dragncards_state(state: Any) -> bool:
    """Whether ``state`` is the raw DragnCards room state this module projects."""
    if not isinstance(state, dict):
        return False
    game = state.get("game")
    return isinstance(game, dict) and isinstance(game.get("cardById"), dict)


def project_state(
    state: Any,
    platform: Platform = PLATFORM_DRAGNCARDS,
    player: str | None = None,
    *,
    seat: str | None = None,
) -> dict[str, Any] | None:
    """Project a recorded state to the judge's view for ``platform``.

    ``player`` is the graded neutral seat. It matters for native marvel-lcg
    world descriptors, whose visibility is seat-specific; ``seat`` is accepted as
    an explicit alias for callers that use the platform-neutral vocabulary.

    Returns ``None`` when the selected platform does not recognise the shape. The
    caller then serialises the recorded value as a bounded raw fallback rather than
    silently dropping content it does not understand.
    """
    graded_seat = player or seat
    if platform == PLATFORM_DRAGNCARDS:
        if not is_raw_dragncards_state(state):
            return None
        game = state["game"]

        projected: dict[str, Any] = {
            key: game[key] for key in _GAME_SCALARS if game.get(key) is not None
        }
        step_id = game.get("stepId")
        description = (
            STEP_DESCRIPTIONS.get(str(step_id)) if step_id is not None else None
        )
        if description:
            projected["stepDescription"] = description

        players = _project_players(game.get("playerData"))
        if players:
            projected["players"] = players
        projected["zones"] = _project_zones(game)
        return projected

    if platform == PLATFORM_MARVEL_LCG:
        return _project_marvel_lcg_state(state, graded_seat)
    return None


def _project_marvel_lcg_state(
    state: Any, graded_seat: str | None
) -> dict[str, Any] | None:
    """Project either the neutral state or a native marvel-lcg world.

    The game-service normally records the neutral state returned by its
    normaliser. Tests, imports, and older producers can still contain the native
    ``WorldDescriptor`` (possibly under ``world``), so that shape is handled here
    as well. In both paths only visible card descriptors are copied; no raw card
    dictionary is ever returned to the judge.
    """
    if not isinstance(state, dict):
        return None

    if _is_normalised_marvel_state(state):
        return _project_normalised_marvel_state(state)

    world = state.get("world")
    if not isinstance(world, dict):
        world = state
    if not _is_native_marvel_world(world):
        return None
    return _project_native_marvel_world(world, graded_seat)


def _is_normalised_marvel_state(state: dict[str, Any]) -> bool:
    return (
        isinstance(state.get("playRound"), int)
        and isinstance(state.get("zones"), dict)
        and isinstance(state.get("players"), dict)
    )


def _is_native_marvel_world(world: dict[str, Any]) -> bool:
    return isinstance(world.get("round_id"), (int, float)) or any(
        key in world
        for key in (
            "area_hero",
            "area_villain",
            "area_schemes_main",
            "hand_cards",
            "player_deck",
        )
    )


def _project_normalised_marvel_state(state: dict[str, Any]) -> dict[str, Any]:
    """Copy only the bounded, neutral marvel-lcg state vocabulary."""
    projected: dict[str, Any] = {}
    for key in (
        "playRound",
        "mode",
        "villainHitPoints",
        "phase",
        "phaseLabel",
        "stepDescription",
        "pendingSeats",
    ):
        value = state.get(key)
        if value is not None:
            projected[key] = value

    players: dict[str, Any] = {}
    for player_id, info in (state.get("players") or {}).items():
        if not isinstance(info, dict):
            continue
        compact = {
            key: info[key]
            for key in ("hitPoints", "handSize", "resources")
            if info.get(key) is not None
        }
        players[str(player_id)] = compact
    projected["players"] = players
    projected["zones"] = _project_normalised_zones(state.get("zones"))
    return projected


def _project_normalised_zones(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    zones: dict[str, list[dict[str, Any]]] = {}
    for zone, cards in value.items():
        if not isinstance(cards, list):
            continue
        visible: list[dict[str, Any]] = []
        hidden_count = 0
        for card in cards:
            if not isinstance(card, dict):
                continue
            name = card.get("name")
            if name == "HIDDEN" or not name:
                hidden_count += _stack_size(card)
                continue
            entry = {
                key: card[key]
                for key in (
                    "id",
                    "instanceId",
                    "name",
                    "type",
                    "currentSide",
                    "exhausted",
                    "tokens",
                    "stackSize",
                )
                if card.get(key) not in (None, {}, False)
            }
            visible.append(entry)
        if hidden_count:
            visible.append({"name": "HIDDEN", "stackSize": hidden_count})
        if visible:
            zones[str(zone)] = visible
    return zones


_MARVEL_ZONE_MAP = {
    "area_schemes_main": "sharedMainScheme",
    "main_schemes_deck": "sharedMainSchemeDeck",
    "area_villain": "sharedVillain",
    "villain_deck": "sharedVillainDeck",
    "encounter_deck": "sharedEncounterDeck",
    "encounter_discard_pile": "sharedEncounterDiscard",
    "area_environment": "sharedEnvironment",
    "area_rule": "sharedRules",
    "area_mission": "sharedMission",
    "area_processing": "sharedProcessing",
    "area_revealing": "sharedRevealing",
    "area_removed": "sharedRemoved",
    "victory_display": "sharedVictory",
}
_MARVEL_PLAYER_ZONE_MAP = {
    "area_hero": "Play1",
    "allies": "Allies",
    "supports": "Supports",
    "player_deck": "Deck",
    "player_discard_pile": "Discard",
    "dealt_encounter_cards": "Encounter",
    "hand_cards": "Hand",
    "engaged_enemies": "Engaged",
    "set_aside_nemesis_sets": "Nemesis",
    "set_aside_deck": "SetAside",
    "obligations_area": "Obligations",
    "environment_area": "Environment",
}


def _project_native_marvel_world(
    world: dict[str, Any], graded_seat: str | None
) -> dict[str, Any]:
    seat_number = _seat_number(graded_seat)
    suppressed_card_instance_ids = _collect_down_card_instance_ids(world)
    projected: dict[str, Any] = {}
    round_id = world.get("round_id")
    if isinstance(round_id, (int, float)) and not isinstance(round_id, bool):
        projected["playRound"] = int(round_id)
    phase_label = str(world.get("phase") or "")
    if phase_label:
        projected["phaseLabel"] = phase_label
        projected["stepDescription"] = phase_label
        projected["phase"] = _marvel_phase(phase_label)
    if world.get("mode") is not None:
        projected["mode"] = world["mode"]
    if world.get("villain_hit_points") is not None:
        projected["villainHitPoints"] = world["villain_hit_points"]

    players: dict[str, Any] = {}
    zones: dict[str, list[dict[str, Any]]] = {}
    raw_players = world.get("players") or []
    if isinstance(raw_players, dict):
        raw_players = list(raw_players.values())
    for index, raw_player in enumerate(raw_players):
        if not isinstance(raw_player, dict):
            continue
        player_id = f"player{index + 1}"
        players[player_id] = {
            key: value
            for key, value in (
                ("handSize", len(raw_player.get("hand_cards") or [])),
                (
                    "hitPoints",
                    raw_player.get("hit_points", raw_player.get("hitPoints")),
                ),
                ("resources", raw_player.get("resources")),
            )
            if value is not None
        }
        for source, suffix in _MARVEL_PLAYER_ZONE_MAP.items():
            zone = _project_native_zone(
                raw_player.get(source), seat_number, suppressed_card_instance_ids
            )
            if zone:
                zones[f"{player_id}{suffix}"] = zone

    for source, target in _MARVEL_ZONE_MAP.items():
        zone = _project_native_zone(
            world.get(source), seat_number, suppressed_card_instance_ids
        )
        if zone:
            zones[target] = zone

    projected["players"] = players
    projected["zones"] = zones
    return projected


def _seat_number(player: str | None) -> int | None:
    if not isinstance(player, str) or not player.startswith("player"):
        return None
    try:
        number = int(player[6:]) - 1
    except ValueError:
        return None
    return number if number in range(4) else None


def _marvel_phase(label: str) -> str:
    value = label.lower()
    if any(
        word in value
        for word in ("mulligan", "setup", "choose hero", "select identity")
    ):
        return "setup"
    if any(word in value for word in ("villain", "encounter", "scheme", "treachery")):
        return "villain"
    if any(word in value for word in ("player", "turn", "player phase")):
        return "player"
    if any(word in value for word in ("resolve", "end of", "passive", "waiting")):
        return "passive"
    return "unknown"


def _project_native_zone(
    value: Any,
    seat_number: int | None,
    suppressed_card_instance_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    hidden_count = 0
    for card in value:
        if not isinstance(card, dict):
            continue
        if card.get("bind_object_id") not in (None, 0, "0", ""):
            continue
        if (
            suppressed_card_instance_ids
            and _native_card_instance_ids(card) & suppressed_card_instance_ids
        ):
            continue
        buried_count = _buried_card_count(card.get("down_card_ids"))
        if not _native_card_visible(card, seat_number):
            hidden_count += 1 + buried_count
            continue
        entry: dict[str, Any] = {
            "id": str(card.get("card_id", card.get("id", "Unknown"))),
            "instanceId": str(card.get("id", "Unknown")),
            "name": str(card.get("name") or card.get("card_id") or "Unknown"),
            "stackSize": 1,
        }
        if card.get("card_type"):
            entry["type"] = str(card["card_type"])
        if card.get("is_ready") is False:
            entry["exhausted"] = True
        info = card.get("info")
        if isinstance(info, dict):
            tokens = {key: item for key, item in info.items() if item}
            if tokens:
                entry["tokens"] = tokens
        result.append(entry)
        # A visible parent remains targetable, but its buried cards are still
        # hidden. Keep their count in the parent's zone instead of inflating the
        # visible parent's stackSize, which would count the same cards twice.
        hidden_count += buried_count
    if hidden_count:
        result.append({"name": "HIDDEN", "stackSize": hidden_count})
    return result


def _iter_native_cards(world: dict[str, Any]):
    raw_players = world.get("players") or []
    if isinstance(raw_players, dict):
        raw_players = list(raw_players.values())
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            continue
        for source in _MARVEL_PLAYER_ZONE_MAP:
            cards = raw_player.get(source)
            if isinstance(cards, (list, tuple)):
                yield from (card for card in cards if isinstance(card, dict))
    for source in _MARVEL_ZONE_MAP:
        cards = world.get(source)
        if isinstance(cards, (list, tuple)):
            yield from (card for card in cards if isinstance(card, dict))


def _down_card_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _buried_card_count(value: Any) -> int:
    """Count distinct buried-card references without exposing their identities."""
    count = 0
    seen_ids: set[str] = set()
    for item in _down_card_items(value):
        identity = _buried_card_identity(item)
        if identity is not None and identity in seen_ids:
            continue
        if identity is not None:
            seen_ids.add(identity)
        count += 1
    return count


def _buried_card_identity(value: Any) -> str | None:
    if not isinstance(value, dict):
        return str(value) if value not in (None, "") else None
    for key in ("id", "instanceId", "object_id", "objectId"):
        if value.get(key) not in (None, ""):
            return str(value[key])
    return None


def _native_card_instance_ids(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return {str(value)} if value not in (None, "") else set()
    return {
        str(value[key])
        for key in ("id", "instanceId", "object_id", "objectId")
        if value.get(key) not in (None, "")
    }


def _collect_down_card_instance_ids(world: dict[str, Any]) -> set[str]:
    """Collect buried physical identities before any native zone is rendered.

    Native Marvel zones can contain both a stack's visible card and the full
    objects named by its ``down_card_ids``. The latter must be suppressed as
    objects, rather than merely counted on the top card, or their names can
    escape into the projected state. Definition-level ``card_id`` values are
    deliberately ignored: another physical copy with the same definition stays
    visible.
    """
    suppressed: set[str] = set()
    for card in _iter_native_cards(world):
        for down_card in _down_card_items(card.get("down_card_ids")):
            suppressed.update(_native_card_instance_ids(down_card))
    return suppressed


def _native_card_visible(card: dict[str, Any], seat_number: int | None) -> bool:
    if "visible_for_players" in card:
        allowed = card["visible_for_players"]
        if seat_number is None:
            return False
        try:
            if seat_number not in {int(item) for item in allowed}:
                return False
        except TypeError, ValueError:
            return False
    return bool(card.get("is_face_up", True))


def _stack_size(card: dict[str, Any]) -> int:
    value = card.get("stackSize", card.get("count", 1))
    try:
        return max(1, int(value))
    except TypeError, ValueError:
        return 1


def _project_players(player_data: Any) -> dict[str, Any]:
    """Per-seat hit points and hand size for seats that are actually occupied."""
    if not isinstance(player_data, dict):
        return {}
    out: dict[str, Any] = {}
    for player_id, info in player_data.items():
        if not isinstance(info, dict) or info.get("alias") is None:
            continue
        out[str(player_id)] = {
            "hitPoints": info.get("hitPoints", 0),
            "handSize": info.get("handSize", 0),
        }
    return out


def _project_zones(game: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group the visible top-of-stack cards by zone, collapsing hidden ones.

    Only the top card of a stack is described (an attachment stack is reported
    with its size), matching how the playing agent sees the table.
    """
    cards = game.get("cardById")
    if not isinstance(cards, dict):
        return {}

    stack_sizes: dict[str, int] = {}
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        stack_id = card.get("stackId")
        if stack_id:
            stack_sizes[stack_id] = stack_sizes.get(stack_id, 0) + 1

    zones: dict[str, list[dict[str, Any]]] = {}
    hidden_counts: dict[str, int] = {}

    for card_id, card in cards.items():
        if not isinstance(card, dict):
            continue
        zone = card.get("groupId")
        if not zone:
            continue
        stack_id = card.get("stackId")
        # Skip cards buried under the top of their stack.
        if stack_id and stack_id != card_id and not stack_id.endswith(f"_{card_id}"):
            continue
        size = stack_sizes.get(stack_id, 1) if stack_id else 1

        side_name = card.get("currentSide", "A")
        sides = card.get("sides")
        side = sides.get(side_name) if isinstance(sides, dict) else None
        side = side if isinstance(side, dict) else {}
        name = side.get("name") or "Unknown"
        exhausted = bool(card.get("exhausted"))
        face_down = card.get("rotation", 0) != 0 and side_name == "A" and not exhausted

        if name in _GENERIC_BACKS or face_down:
            hidden_counts[str(zone)] = hidden_counts.get(str(zone), 0) + size
            continue

        entry: dict[str, Any] = {"instanceId": str(card_id), "name": name}
        for source_key, out_key in (
            ("type", "type"),
            ("stage", "stage"),
            ("traits", "traits"),
        ):
            value = side.get(source_key)
            if value:
                entry[out_key] = value
        tokens = card.get("tokens")
        if isinstance(tokens, dict):
            live = {k: v for k, v in tokens.items() if v}
            if live:
                entry["tokens"] = live
        if exhausted:
            entry["exhausted"] = True
        if side_name != "A":
            entry["side"] = side_name
        if size > 1:
            entry["stackSize"] = size
        zones.setdefault(str(zone), []).append(entry)

    for zone, count in hidden_counts.items():
        zones.setdefault(zone, []).append({"name": "HIDDEN", "count": count})
    return zones


def render_state(
    value: Any,
    max_chars: int,
    *,
    label: str,
    platform: Platform = PLATFORM_DRAGNCARDS,
    player: str | None = None,
    seat: str | None = None,
) -> str:
    """Render a recorded state for a judge prompt, bounded by ``max_chars``.

    Projects the raw DragnCards shape first (a ~180x reduction on real games) and
    only then applies the character bound as a backstop. States in an unknown
    shape are serialised as recorded, preserving the previous behaviour. Any
    truncation is marked in the text and logged so it stays observable.
    """
    projected = project_state(value, platform, player, seat=seat)
    if projected is not None:
        rendered = canonical_json(projected)
        kind = "projected"
    elif platform == PLATFORM_MARVEL_LCG:
        # An unrecognised native Marvel shape may contain seat-private card data.
        # Do not send the raw payload as a fallback; an explicit marker is safer
        # than allowing a future schema change to bypass the visibility filter.
        rendered = canonical_json(
            {"platform": PLATFORM_MARVEL_LCG, "state": "unavailable"}
        )
        kind = "unavailable"
    else:
        rendered = canonical_json(value)
        kind = "raw"

    if max_chars > 0 and len(rendered) > max_chars:
        logger.info(
            "Truncated %s %s state JSON from %d to %d chars for judge input",
            kind,
            label,
            len(rendered),
            max_chars,
        )
        return (
            rendered[:max_chars]
            + f"\n...[truncated {len(rendered) - max_chars} chars of {label} state]"
        )
    return rendered
