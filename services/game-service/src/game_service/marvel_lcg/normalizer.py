"""Convert the marvel-lcg world descriptor to the neutral game state."""

from __future__ import annotations

import re
from typing import Any, Iterable

from game_service.api.models import SimplifiedCard
from game_service.marvel_lcg.options import _visible

_ZONE_MAP = {
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


def _phase(label: str) -> str:
    value = label.lower()
    if not value:
        return "unknown"
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


def _resource_count(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*", value)
        if match:
            return int(match.group(1))
    return None


class MarvelLcgNormaliser:
    """Normaliser with one explicit reading seat for private-card visibility.

    A multi-seat session may own several sockets, but the engine's card
    visibility is evaluated from one reader at a time.  Unioning all held seats
    would disclose a card visible only to another player, so the default view
    deliberately uses the first configured seat unless a caller selects one.
    """

    def __init__(
        self,
        seats: Iterable[str] = ("player1",),
        *,
        reading_seat: str | None = None,
    ) -> None:
        self.seats = tuple(seats)
        self.reading_seat = reading_seat or (self.seats[0] if self.seats else "player1")

    @property
    def seat_numbers(self) -> tuple[int, ...]:
        result: list[int] = []
        try:
            result.append(int(self.reading_seat[6:]) - 1)
        except ValueError, TypeError:
            return ()
        return tuple(number for number in result if number in range(4))

    def _card(self, card: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(card, dict):
            return None
        if card.get("bind_object_id") not in (None, 0, "0", ""):
            # Attached/tucked cards are represented by their host, not as a
            # second card in the neutral zone listing.
            return None
        visible = _visible(card, self.seat_numbers)
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
        info = card.get("info")
        if isinstance(info, dict):
            tokens = {key: value for key, value in info.items() if value}
            if tokens:
                result["tokens"] = tokens
        return SimplifiedCard(**result).model_dump(exclude_defaults=True) | {
            "stackSize": stack_size
        }

    def _zone(self, cards: Any) -> list[dict[str, Any]]:
        if not isinstance(cards, (list, tuple)):
            return []
        result: list[dict[str, Any]] = []
        hidden = 0
        for card in cards:
            if not isinstance(card, dict):
                continue
            compact = self._card(card)
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
        self, raw_state: Any, *, plugin_name: str | None = None
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
        phase_label = str(world.get("phase", "") or "")
        zones: dict[str, list[dict[str, Any]]] = {}
        for source, target in _ZONE_MAP.items():
            zones[target] = self._zone(world.get(source, []))

        players: dict[str, dict[str, Any]] = {}
        raw_players = world.get("players") or []
        if isinstance(raw_players, dict):
            raw_players = list(raw_players.values())
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
                zones[f"{seat}{suffix}"] = self._zone(player.get(source, []))

        pending = []
        for item in world.get("_ask_players", frame.get("ask_players", [])) or []:
            try:
                pending.append(f"player{int(item) + 1}")
            except TypeError, ValueError:
                pending.append(str(item))
        mode = world.get("mode")
        if not isinstance(mode, str):
            mode = "loss" if frame.get("render_id") == -1 else "in progress"
        result: dict[str, Any] = {
            "playRound": int(world.get("round_id", 0) or 0),
            "mode": mode,
            "villainHitPoints": int(world.get("villain_hit_points", 0) or 0),
            "stepId": frame.get("current_step_id"),
            "stepDescription": phase_label or None,
            "phase": _phase(phase_label),
            "phaseLabel": phase_label or None,
            "players": players,
            "zones": {key: value for key, value in zones.items() if value},
        }
        # This is intentionally present for marvel-lcg and absent for DragnCards.
        result["pendingSeats"] = pending
        return result
