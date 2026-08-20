"""Per-platform state normalisation.

The router should not know how a platform represents phases, rounds, or cards.
This module keeps the existing DragnCards projection intact and adds the neutral
fields consumed by platform-aware callers.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from game_service.api.models import SimplifiedCard
from game_service.logic.platform import (
    DRAGNCARDS_PLATFORM,
    MARVEL_LCG_PLATFORM,
    PlatformSlug,
)

Phase = Literal["setup", "player", "villain", "passive", "unknown"]

STEP_DESCRIPTIONS: dict[str, str] = {
    "step-0.0": "Beginning of Round",
    "step-0.1": "End of Round",
    "step-1.1": "Player Turn",
    "step-1.2": "End of Player Phase",
    "step-2.1": "Place threat on the main scheme.",
    "step-2.2": "The villain activates once per player, along with any eligible minions",
    "step-2.3": "Deal one encounter card to each player.",
    "step-2.4": "Reveal encounter cards.",
    "step-2.5": "Pass the first player token and end the round.",
}


class StateNormaliser(Protocol):
    """Produce the neutral state view for a platform."""

    def normalise(self, raw_state: Any, *, plugin_name: str | None = None) -> Any: ...


def _get_step_description(step_id: str | int | None) -> str | None:
    if step_id is None:
        return None
    return STEP_DESCRIPTIONS.get(f"step-{step_id}")


def _compact_tokens(tokens: dict | None) -> dict:
    if not tokens:
        return {}
    return {key: value for key, value in tokens.items() if value}


def _phase_for_step(step_id: str | int | None) -> Phase:
    if step_id is None:
        return "unknown"
    value = str(step_id)
    if value in {"1.1", "1.2"}:
        return "player"
    if value in {"2.1", "2.2", "2.3", "2.4", "2.5"}:
        return "villain"
    if value in {"0.0", "0.1"}:
        return "passive"
    return "unknown"


def simplify_dragncards_marvel_state(raw_state: dict[str, Any]) -> dict[str, Any]:
    """Transform raw DragnCards Marvel Champions state into a compact view.

    The legacy state projection is retained except for the completed-round
    counter: the neutral contract exposes ``playRound`` and deliberately does
    not leak DragnCards' raw ``roundNumber``.
    """
    game = raw_state.get("game", {}) if isinstance(raw_state, dict) else {}
    if not game:
        return {"mode": "unknown"}

    player_data = game.get("playerData", {})
    players: dict[str, dict[str, int]] = {}
    for player_id, p_info in player_data.items():
        if p_info.get("alias") is None:
            continue
        players[player_id] = {
            "hitPoints": p_info.get("hitPoints", 0),
            "handSize": p_info.get("handSize", 0),
        }

    card_data = game.get("cardById", {})
    zones: dict[str, list[dict[str, Any]]] = {}
    stack_card_counts: dict[str, int] = {}
    for c_info in card_data.values():
        stack_id = c_info.get("stackId", "")
        if stack_id:
            stack_card_counts[stack_id] = stack_card_counts.get(stack_id, 0) + 1

    hidden_cards_per_zone: dict[str, int] = {}
    for card_id, c_info in card_data.items():
        zone_id = c_info.get("groupId")
        if not zone_id:
            continue

        stack_id = c_info.get("stackId")
        if stack_id and stack_id != card_id and not stack_id.endswith("_" + card_id):
            continue

        stack_size = stack_card_counts.get(stack_id, 1) if stack_id else 1
        current_side = c_info.get("currentSide", "A")
        sides = c_info.get("sides", {})
        side_info = sides.get(current_side, {})
        card_name = side_info.get("name", "Unknown")
        rotation = c_info.get("rotation", 0)
        exhausted = c_info.get("exhausted", False)

        is_player_encounter = card_name in ("player", "encounter")
        is_facedown = rotation != 0 and current_side == "A" and not exhausted
        if is_player_encounter or is_facedown:
            hidden_cards_per_zone[zone_id] = (
                hidden_cards_per_zone.get(zone_id, 0) + stack_size
            )
            continue

        card_details: dict[str, Any] = {
            "id": c_info.get("databaseId", "Unknown"),
            "instanceId": card_id,
            "name": card_name,
        }
        if current_side != "A":
            card_details["currentSide"] = current_side
        if exhausted:
            card_details["exhausted"] = True
        non_zero_tokens = _compact_tokens(c_info.get("tokens"))
        if non_zero_tokens:
            card_details["tokens"] = non_zero_tokens
        card_details["stackSize"] = stack_size

        compact = SimplifiedCard(**card_details).model_dump(exclude_defaults=True)
        compact.setdefault("stackSize", stack_size)
        zones.setdefault(zone_id, []).append(compact)

    for zone_id, hidden_count in hidden_cards_per_zone.items():
        zones.setdefault(zone_id, []).append(
            {"name": "HIDDEN", "stackSize": hidden_count}
        )

    step_id = game.get("stepId")
    round_number = game.get("roundNumber", 0)
    try:
        play_round = int(round_number) + 1
    except TypeError, ValueError:
        play_round = 1
    step_description = _get_step_description(step_id)
    return {
        "playRound": play_round,
        "mode": game.get("mode", "unknown"),
        "villainHitPoints": game.get("villainHitPoints", 0),
        "stepId": step_id,
        "stepDescription": step_description,
        "phase": _phase_for_step(step_id),
        "phaseLabel": step_description,
        "players": players,
        "zones": zones,
    }


class DragnCardsNormaliser:
    platform: PlatformSlug = DRAGNCARDS_PLATFORM

    def normalise(self, raw_state: Any, *, plugin_name: str | None = None) -> Any:
        if plugin_name is not None and plugin_name != "marvel-champions":
            return raw_state
        return simplify_dragncards_marvel_state(raw_state)


class IdentityNormaliser:
    def normalise(self, raw_state: Any, *, plugin_name: str | None = None) -> Any:
        del plugin_name
        return raw_state


STATE_NORMALISERS: dict[PlatformSlug, StateNormaliser] = {
    DRAGNCARDS_PLATFORM: DragnCardsNormaliser(),
}


def get_state_normaliser(platform: str) -> StateNormaliser:
    """Return a normaliser without importing platform data at module import."""
    if platform == MARVEL_LCG_PLATFORM:
        from game_service.marvel_lcg.normalizer import MarvelLcgNormaliser

        return MarvelLcgNormaliser()
    return STATE_NORMALISERS.get(platform, IdentityNormaliser())


# American spelling is useful to callers outside this codebase while the public
# design vocabulary remains ``normaliser``.
StateNormalizer = StateNormaliser
get_state_normalizer = get_state_normaliser
