"""Router: game state and snapshot endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from game_service.api.deps import get_manager
from game_service.api.models import (
    GameStateSnapshot,
    GameStateResponse,
    SimplifiedGameState,
)
from game_service.logic.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["game-state"])


def _simplify_marvel_state(raw_state: dict) -> SimplifiedGameState:
    """Transform raw DragnCards Marvel Champions state into a simplified representation."""
    game = raw_state.get("game", {})
    if not game:
        return SimplifiedGameState(mode="unknown")

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
    group_by_id = game.get("groupById", {})
    zones: dict[str, list[dict]] = {}

    # Group cards by stackId to compute stack sizes
    stack_card_counts: dict[str, int] = {}
    for c_info in card_data.values():
        stack_id = c_info.get("stackId", "")
        if stack_id:
            stack_card_counts[stack_id] = stack_card_counts.get(stack_id, 0) + 1

    # Track hidden cards per zone for merging (facedown + player/encounter cards)
    hidden_cards_per_zone: dict[str, dict] = {}

    # Build a lookup for card_id by stackId
    card_id_by_stack_id: dict[str, str] = {}
    for card_id, c_info in card_data.items():
        stack_id = c_info.get("stackId")
        # Only topmost card has stackId ending with "_" + card_id or stackId == card_id
        if stack_id and (stack_id == card_id or stack_id.endswith("_" + card_id)):
            card_id_by_stack_id[stack_id] = card_id

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
            if zone_id not in hidden_cards_per_zone:
                hidden_cards_per_zone[zone_id] = {
                    "count": 0,
                    "first_instance_id": card_id,
                }
            hidden_cards_per_zone[zone_id]["count"] += stack_size
            continue

        card_details = {
            "id": c_info.get("databaseId", "Unknown"),
            "instanceId": card_id,
            "name": card_name,
            "currentSide": current_side,
            "exhausted": c_info.get("exhausted", False),
            "tokens": c_info.get("tokens", {}),
            "stackSize": stack_size,
        }

        if zone_id not in zones:
            zones[zone_id] = []
        zones[zone_id].append(card_details)

    # Add merged hidden cards to zones using stackIds ordering
    for zone_id, hidden_info in hidden_cards_per_zone.items():
        if zone_id not in zones:
            zones[zone_id] = []
        # Get the first stackId from groupById ordering to determine instanceId and currentSide
        group_data = group_by_id.get(zone_id, {})
        stack_ids = group_data.get("stackIds", [])
        first_stack_id = stack_ids[0] if stack_ids else hidden_info["first_instance_id"]
        # Get the card_id for this stack_id
        first_instance_id = card_id_by_stack_id.get(
            first_stack_id, hidden_info["first_instance_id"]
        )
        # Get the card data for the first card to inherit currentSide
        first_card_data = card_data.get(first_instance_id, {})
        inherited_current_side = first_card_data.get("currentSide", "A")
        zones[zone_id].append(
            {
                "id": "Unknown",
                "instanceId": first_instance_id,
                "name": "HIDDEN",
                "currentSide": inherited_current_side,
                "exhausted": False,
                "tokens": {},
                "stackSize": hidden_info["count"],
            }
        )

    return SimplifiedGameState(
        roundNumber=game.get("roundNumber", 0),
        mode=game.get("mode", "unknown"),
        villainHitPoints=game.get("villainHitPoints", 0),
        stepId=game.get("stepId"),
        players=players,
        zones=zones,
    )


@router.get(
    "/games/{session_id}/state/raw",
    summary="DEBUG ONLY: Get raw game state without simplification",
    operation_id="get_raw_game_state_games",
)
async def get_raw_game_state(
    session_id: str,
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
    session_id: str,
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
    session_id: str,
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
    session_id: str,
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
