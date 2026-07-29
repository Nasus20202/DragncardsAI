"""Router: game state and snapshot endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends

from game_service.api.deps import SessionIdentifier, get_manager
from game_service.api.models import (
    GameStateSnapshot,
    GameStateResponse,
    SimplifiedCard,
)
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-state"])

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


def _get_step_description(step_id: str | int | None) -> str | None:
    """Convert a step ID to its human-readable description."""
    if step_id is None:
        return None
    step_key = f"step-{step_id}"
    return STEP_DESCRIPTIONS.get(step_key)


def _compact_tokens(tokens: dict | None) -> dict:
    """Return a tokens dict containing only the non-zero counters.

    The simplified card shape keeps `tokens` only when at least one counter
    is non-zero; an empty result here means the caller should drop the
    `tokens` field entirely from the emitted card.
    """
    if not tokens:
        return {}
    return {key: value for key, value in tokens.items() if value}


def _simplify_marvel_state(raw_state: dict) -> dict[str, Any]:
    """Transform raw DragnCards Marvel Champions state into a simplified representation.

    The output is compact: visible cards only carry the fields that carry
    information (`id`, `instanceId`, `name`, `stackSize` plus the
    non-default `currentSide`, `exhausted`, and `tokens` fields), and HIDDEN
    entries collapse to `{name: "HIDDEN", stackSize: N}`. See
    `openspec/specs/simplified-game-state/spec.md` for the full shape.

    Returns a plain dict rather than a `SimplifiedGameState` Pydantic model
    so the per-card fields with default values stay omitted (Pydantic would
    re-fill them on validation, undoing the compaction). Callers wrap the
    dict in `GameStateResponse` (or the equivalent response model) which
    accepts `Union[SimplifiedGameState, dict]`.
    """
    game = raw_state.get("game", {})
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

    # Group cards by stackId to compute stack sizes
    stack_card_counts: dict[str, int] = {}
    for c_info in card_data.values():
        stack_id = c_info.get("stackId", "")
        if stack_id:
            stack_card_counts[stack_id] = stack_card_counts.get(stack_id, 0) + 1

    # Track hidden cards per zone for merging (facedown + player/encounter cards)
    hidden_cards_per_zone: dict[str, int] = {}

    for card_id, c_info in card_data.items():
        zone_id = c_info.get("groupId")
        if not zone_id:
            continue

        stack_id = c_info.get("stackId")

        # Skip cards that are not the top of their stack
        if stack_id and stack_id != card_id and not stack_id.endswith("_" + card_id):
            continue

        stack_size = stack_card_counts.get(stack_id, 1) if stack_id else 1

        current_side = c_info.get("currentSide", "A")
        sides = c_info.get("sides", {})
        side_info = sides.get(current_side, {})
        card_name = side_info.get("name", "Unknown")

        rotation = c_info.get("rotation", 0)
        exhausted = c_info.get("exhausted", False)

        # Determine if card should be hidden
        # - Player/encounter cards are hidden (they represent identity, e.g., villain in hero deck)
        # - Facedown cards (Side A with rotation != 0, not exhausted) are hidden
        # - Exhausted cards (Side B with exhausted=True) remain visible - exhaustion doesn't hide them
        is_player_encounter = card_name in ("player", "encounter")
        is_facedown = rotation != 0 and current_side == "A" and not exhausted

        if is_player_encounter or is_facedown:
            hidden_cards_per_zone[zone_id] = (
                hidden_cards_per_zone.get(zone_id, 0) + stack_size
            )
            continue

        # Build a card payload with only the fields that carry information.
        # Pydantic's `exclude_defaults=True` then drops any field that matches
        # the SimplifiedCard schema default, so a face-up unexhausted card
        # with no tokens is just `{id, instanceId, name, stackSize}`.
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
        # `stackSize` is always meaningful for a top-of-stack card; re-attach
        # it in case it matched the schema default (1) and was dropped.
        compact.setdefault("stackSize", stack_size)
        if zone_id not in zones:
            zones[zone_id] = []
        zones[zone_id].append(compact)

    # Add merged hidden cards to zones. A HIDDEN entry is just
    # {name: "HIDDEN", stackSize: N} — the agent never needs to target
    # face-down cards, and the count is the only thing it acts on.
    for zone_id, hidden_count in hidden_cards_per_zone.items():
        if zone_id not in zones:
            zones[zone_id] = []
        zones[zone_id].append({"name": "HIDDEN", "stackSize": hidden_count})

    return {
        "roundNumber": game.get("roundNumber", 0),
        "mode": game.get("mode", "unknown"),
        "villainHitPoints": game.get("villainHitPoints", 0),
        "stepId": game.get("stepId"),
        "stepDescription": _get_step_description(game.get("stepId")),
        "players": players,
        "zones": zones,
    }


@router.get(
    "/games/{session_id}/state/raw",
    summary="DEBUG ONLY: Get raw game state without simplification",
    operation_id="get_raw_game_state_games",
)
async def get_raw_game_state(
    session_id: SessionIdentifier,
    manager: SessionManager = Depends(get_manager),
):
    """Get the raw game state without any simplification or transformation."""
    logger.info("get_raw_game_state: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        return await session.get_state()


@router.get(
    "/games/{session_id}/state",
    response_model=GameStateResponse,
    summary="Get current game state",
    operation_id="get_game_state",
)
async def get_game_state(
    session_id: SessionIdentifier,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("get_game_state: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        state = await session.get_state()

    logger.debug(
        "get_game_state: session_id=%s -> state keys=%s",
        session_id,
        list(state.keys()) if isinstance(state, dict) else type(state).__name__,
    )

    # Apply simplified state for Marvel Champions
    if session.plugin_name == "marvel-champions":
        state = _simplify_marvel_state(state)

    return GameStateResponse(session_id=session_id, state=state)


@router.get(
    "/games/{session_id}/snapshot",
    response_model=GameStateSnapshot,
    summary="Export a reusable game state snapshot",
    operation_id="export_game_state_snapshot",
)
async def export_game_state_snapshot(
    session_id: SessionIdentifier,
    manager: SessionManager = Depends(get_manager),
):
    logger.info("export_game_state_snapshot: session_id=%s", session_id)
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        return await session.export_state()


@router.put(
    "/games/{session_id}/snapshot",
    response_model=GameStateResponse,
    summary="Load a game state snapshot",
    operation_id="load_game_state_snapshot",
)
async def load_game_state_snapshot(
    session_id: SessionIdentifier,
    snapshot: GameStateSnapshot,
    manager: SessionManager = Depends(get_manager),
):
    logger.info(
        "load_game_state_snapshot: session_id=%s plugin_name=%r schema_version=%s",
        session_id,
        snapshot.plugin_name,
        snapshot.schema_version,
    )
    async with manager.session_operation_lock(session_id):
        session = await manager.get_session(session_id)
        state = await session.load_state(snapshot)

    # Apply simplified state for Marvel Champions
    if session.plugin_name == "marvel-champions":
        state = _simplify_marvel_state(state)

    return GameStateResponse(session_id=session_id, state=state)
