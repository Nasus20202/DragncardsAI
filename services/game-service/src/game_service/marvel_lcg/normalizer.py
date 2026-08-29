"""Convert the marvel-lcg world descriptor to the neutral game state."""

from __future__ import annotations

import re
from typing import Any, Iterable

from game_service.api.models import SimplifiedCard
from game_service.marvel_lcg.options import _visible

_ZONE_MAP = {
    "area_schemes_main": "sharedMainScheme",
    "area_schemes_side": "sharedSideSchemes",
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
_PLAYER_ZONE_MAP = {
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


_PHASES = {
    "initialize": "setup",
    "scenario setup": "setup",
    "resolve mulligans": "setup",
    "init finished": "setup",
    "player turn": "player",
    "player turn end": "player",
    "main scheme place threat": "villain",
    "enemy activation": "villain",
    "deal encounter cards": "villain",
    "reveal encounter cards": "villain",
    "end phase": "passive",
    "end round": "passive",
    "start round": "passive",
}

_INFO_KEY_MAP = {
    "k_threat": "threat",
    "c_damage": "damage",
    "k_damage": "damage",
    "c_threat": "threat",
    "k_acceleration_token": "acceleration",
    "acceleration_icon": "acceleration",
}


def _phase(label: str) -> str:
    value = label.strip().lower()
    if not value:
        return "unknown"
    phase = _PHASES.get(value)
    if phase is not None:
        return phase
    if re.fullmatch(r"player \d+ turn", value):
        return "player"
    return "unknown"


def _normalise_info(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in info.items():
        if not value:
            continue
        result[_INFO_KEY_MAP.get(str(key), str(key))] = value
    return result


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d+\s*", value):
        return int(value)
    return None


def _active_villain_hit_points(
    cards: Any, visible_seats: Iterable[int]
) -> int | None:
    if not isinstance(cards, (list, tuple)):
        return None
    for card in cards:
        if not isinstance(card, dict):
            continue
        if card.get("bind_object_id") not in (None, 0, "0", ""):
            continue
        card_type = str(card.get("card_type", "")).lower()
        if card_type and card_type not in {"villain", "enemy", "encountervillain"}:
            continue
        if not _visible(card, visible_seats):
            continue
        info = card.get("info")
        if isinstance(info, dict):
            health = _integer(info.get("health"))
            damage = (
                _integer(info.get("c_damage"))
                or _integer(info.get("k_damage"))
                or _integer(info.get("damage"))
                or 0
            )
            if health is not None:
                return health + damage
    return None


def _resource_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*", value)
        if match:
            return int(match.group(1))
    return None


class MarvelLcgNormaliser:
    """Stateless normaliser for the Marvel engine's per-call reader projection."""

    def __init__(self, seats: Iterable[str] = ("player1",)) -> None:
        self.seats = tuple(seats)

    @staticmethod
    def _seat_number(player_n: str | None) -> tuple[int, ...]:
        if player_n is None:
            return ()
        result: list[int] = []
        try:
            result.append(int(player_n[6:]) - 1)
        except ValueError, TypeError:
            return ()
        return tuple(number for number in result if number in range(4))

    def _card(
        self,
        card: dict[str, Any],
        visible_seats: Iterable[int],
        *,
        require_all: bool = False,
        force_hidden: bool = False,
        require_face_up: bool = True,
    ) -> dict[str, Any] | None:
        if not isinstance(card, dict):
            return None
        if card.get("bind_object_id") not in (None, 0, "0", ""):
            # Attached/tucked cards are represented by their host, not as a
            # second card in the neutral zone listing.
            return None
        visible = _visible(
            card,
            visible_seats,
            require_all=require_all,
            require_face_up=require_face_up,
        )
        if force_hidden:
            visible = False
        down = card.get("down_card_ids") or []
        stack_size = 1 + len(down)
        if not visible:
            return {"name": "HIDDEN", "stackSize": stack_size}
        name = str(card.get("name") or card.get("card_id") or "Unknown")
        card_type = card.get("card_type")
        result: dict[str, Any] = {
            "id": str(card.get("card_id", card.get("id", "Unknown"))),
            "instanceId": str(card.get("id", "Unknown")),
            "name": name,
            "stackSize": stack_size,
        }
        if card_type:
            result["type"] = str(card_type)
        if not card.get("is_ready", True):
            result["exhausted"] = True
        info = _normalise_info(card.get("info"))
        if info:
            result["tokens"] = info
        return SimplifiedCard(**result).model_dump(exclude_defaults=True) | {
            "stackSize": stack_size
        }

    def _zone(
        self,
        cards: Any,
        visible_seats: Iterable[int],
        *,
        require_all: bool = False,
        force_hidden: bool = False,
        require_face_up: bool = True,
    ) -> list[dict[str, Any]]:
        if not isinstance(cards, (list, tuple)):
            return []
        result: list[dict[str, Any]] = []
        hidden = 0
        for card in cards:
            if not isinstance(card, dict):
                continue
            compact = self._card(
                card,
                visible_seats,
                require_all=require_all,
                force_hidden=force_hidden,
                require_face_up=require_face_up,
            )
            if compact is None:
                continue
            if compact.get("name") == "HIDDEN":
                hidden += int(compact.get("stackSize", 1))
            else:
                result.append(compact)
        if hidden:
            result.append({"name": "HIDDEN", "stackSize": hidden})
        return result

    def normalise(
        self,
        raw_state: Any,
        *,
        plugin_name: str | None = None,
        player_n: str | None = None,
    ) -> dict[str, Any]:
        del plugin_name
        if not isinstance(raw_state, dict):
            raise ValueError("marvel-lcg world is not an object")
        frame = (
            raw_state.get("_frame") if isinstance(raw_state.get("_frame"), dict) else {}
        )
        world = (
            raw_state.get("world")
            if isinstance(raw_state.get("world"), dict)
            else raw_state
        )
        if not isinstance(world, dict):
            raise ValueError("marvel-lcg world is not an object")
        visible_seats = self._seat_number(player_n)
        raw_players = world.get("players") or []
        if isinstance(raw_players, dict):
            raw_players = list(raw_players.values())
        spectator = player_n is None
        spectator_seats = tuple(range(min(len(raw_players), 4))) if spectator else ()
        phase_label = str(world.get("phase", "") or "")
        zones: dict[str, list[dict[str, Any]]] = {}
        for source, target in _ZONE_MAP.items():
            zones[target] = self._zone(
                world.get(source, []),
                visible_seats or spectator_seats,
                require_all=spectator,
            )

        players: dict[str, dict[str, Any]] = {}
        for index, player in enumerate(raw_players):
            if not isinstance(player, dict):
                continue
            seat = f"player{index + 1}"
            player_view: dict[str, Any] = {
                "handSize": len(player.get("hand_cards") or []),
            }
            resource_count = _resource_count(player.get("resources"))
            if resource_count is not None:
                player_view["resources"] = resource_count
            if "hit_points" in player or "hitPoints" in player:
                player_view["hitPoints"] = player.get(
                    "hit_points", player.get("hitPoints", 0)
                )
            players[seat] = player_view
            for source, suffix in _PLAYER_ZONE_MAP.items():
                zones[f"{seat}{suffix}"] = self._zone(
                    player.get(source, []),
                    visible_seats or spectator_seats,
                    require_all=spectator,
                    force_hidden=source == "hand_cards"
                    and (spectator or seat != player_n),
                    require_face_up=source != "hand_cards",
                )

        pending = []
        for item in world.get("_ask_players", frame.get("ask_players", [])) or []:
            try:
                pending.append(f"player{int(item) + 1}")
            except TypeError, ValueError:
                pending.append(str(item))
        mode = world.get("mode")
        if not isinstance(mode, str):
            mode = "loss" if frame.get("render_id") == -1 else "in progress"
        villain_hit_points = _active_villain_hit_points(
            world.get("area_villain", []),
            visible_seats or spectator_seats,
        )
        if villain_hit_points is None:
            # Keep compatibility with an engine variant that explicitly reports
            # a world-level value, but never turn an absent value into zero.
            villain_hit_points = _integer(world.get("villain_hit_points"))
        result: dict[str, Any] = {
            "playRound": int(world.get("round_id", 0) or 0),
            "mode": mode,
            "stepId": frame.get("current_step_id"),
            "stepDescription": phase_label or None,
            "phase": _phase(phase_label),
            "phaseLabel": phase_label or None,
            "players": players,
            "zones": {key: value for key, value in zones.items() if value},
        }
        if villain_hit_points is not None:
            result["villainHitPoints"] = villain_hit_points
        # This is intentionally present for marvel-lcg and absent for DragnCards.
        result["pendingSeats"] = pending
        return result
