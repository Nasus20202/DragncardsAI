from __future__ import annotations

from unittest.mock import AsyncMock

from game_service.api.routers.game_state import _simplify_marvel_state
from game_service.logic.session_manager import BadGameStateError, StateUnavailableError

from .game_room_state_test_support import (
    SESSION_ID,
    make_client,
    mock_manager,
    mock_session,
)


async def test_get_game_state_200():
    async with make_client() as client:
        response = await client.get(f"/games/{SESSION_ID}/state")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == SESSION_ID
    # Simplified format has flat keys (not nested under 'game')
    assert body["state"]["roundNumber"] == 1
    assert "game" not in body["state"]


async def test_bad_game_state_error_returns_409():
    session = mock_session()
    session.get_state = AsyncMock(
        side_effect=BadGameStateError("game state is corrupted")
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")
    assert response.status_code == 409
    assert "corrupted" in response.json()["detail"]


async def test_state_unavailable_error_returns_503():
    session = mock_session()
    session.get_state = AsyncMock(
        side_effect=StateUnavailableError("state temporarily unavailable")
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")
    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


async def test_export_snapshot_200():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == 1
    assert body["plugin_name"] == "marvel-champions"
    assert body["game"]["roundNumber"] == 0


async def test_load_snapshot_200():
    session = mock_session()
    async with make_client(mock_manager(session)) as client:
        response = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "marvel-champions",
                "game": {"roundNumber": 2},
            },
        )
    assert response.status_code == 200
    session.load_state.assert_awaited_once()
    assert response.json()["state"]["roundNumber"] == 2


async def test_load_snapshot_validation_error_returns_400():
    from game_service.logic.session_manager import SnapshotValidationError

    session = mock_session()
    session.load_state = AsyncMock(
        side_effect=SnapshotValidationError("plugin mismatch")
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.put(
            f"/games/{SESSION_ID}/snapshot",
            json={
                "schema_version": 1,
                "plugin_name": "other-game",
                "game": {},
            },
        )
    assert response.status_code == 400
    assert "plugin mismatch" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Simplified state tests
# ---------------------------------------------------------------------------


def test_simplify_marvel_state_extracts_essential_fields():
    raw = {
        "game": {
            "roundNumber": 3,
            "mode": "villain",
            "villainHitPoints": 8,
            "playerData": {
                "player1": {"alias": "Spider-Man", "hitPoints": 10, "handSize": 5},
                "player2": {"alias": None, "hitPoints": 8, "handSize": 3},
            },
            "cardById": {
                "card-abc": {
                    "databaseId": "uuid-123",
                    "currentSide": "A",
                    "groupId": "player1Hand",
                    "stackId": "card-abc",
                    "sides": {"A": {"name": "Web Shooters"}},
                    "exhausted": False,
                    "tokens": {"damage": 1},
                },
                "card-def": {
                    "databaseId": "uuid-456",
                    "currentSide": "B",
                    "groupId": "sharedVillainDeck",
                    "stackId": "card-def",
                    "sides": {"B": {"name": "Goblin Minions"}},
                    "exhausted": True,
                    "tokens": {},
                },
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    assert result_dict["roundNumber"] == 3
    assert result_dict["mode"] == "villain"
    assert result_dict["villainHitPoints"] == 8
    assert "player1" in result_dict["players"]
    assert "player2" not in result_dict["players"]  # null alias filtered out
    assert result_dict["players"]["player1"]["hitPoints"] == 10
    assert result_dict["players"]["player1"]["handSize"] == 5

    # Cards mapped to zones
    assert "player1Hand" in result_dict["zones"]
    assert len(result_dict["zones"]["player1Hand"]) == 1
    card = result_dict["zones"]["player1Hand"][0]
    assert card["id"] == "uuid-123"
    assert card["instanceId"] == "card-abc"
    assert card["name"] == "Web Shooters"
    assert card["currentSide"] == "A"
    assert card["exhausted"] is False
    assert card["tokens"] == {"damage": 1}
    assert card["stackSize"] == 1


def test_simplify_marvel_state_filters_tucked_attachments():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "parent-card": {
                    "databaseId": "parent-uuid",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "parent-card",
                    "sides": {"A": {"name": "Parent Card"}},
                    "exhausted": False,
                    "tokens": {},
                },
                "attachment-card": {
                    "databaseId": "attach-uuid",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "parent-card::attachment-card",
                    "sides": {"A": {"name": "Attachment"}},
                    "exhausted": False,
                    "tokens": {},
                },
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Only parent card appears, attachment is tucked (stackId differs from card_id)
    assert len(result_dict["zones"]["player1Play1"]) == 1
    assert result_dict["zones"]["player1Play1"][0]["name"] == "Parent Card"


def test_simplify_marvel_state_includes_stack_size():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-a": {
                    "databaseId": "uuid-a",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "s_stack_card-a",
                    "sides": {"A": {"name": "Hero"}},
                    "exhausted": False,
                    "tokens": {},
                },
                "card-b": {
                    "databaseId": "uuid-b",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "s_stack_card-a",
                    "sides": {"A": {"name": "Upgrade"}},
                    "exhausted": False,
                    "tokens": {},
                },
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Both cards share the same stackId, only one card appears with stack size 2
    assert "player1Play1" in result_dict["zones"]
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card["name"] == "Hero"
    assert card["stackSize"] == 2


def test_simplify_marvel_state_hides_facedown_cards():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-a": {
                    "databaseId": "uuid-a",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "card-a",
                    "sides": {"A": {"name": "Hero"}},
                    "exhausted": False,
                    "tokens": {},
                    "rotation": 180,
                },
            },
            "groupById": {
                "player1Play1": {
                    "stackIds": ["card-a"],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Facedown card (Side A with rotation) shows only stack size with name HIDDEN
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card["name"] == "HIDDEN"
    assert card["id"] == "Unknown"
    assert card["instanceId"] == "card-a"
    assert card["currentSide"] == "A"
    assert card["stackSize"] == 1


def test_simplify_marvel_state_shows_exhausted_cards():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-exhausted": {
                    "databaseId": "uuid-exhausted",
                    "currentSide": "B",
                    "groupId": "player1Play1",
                    "stackId": "card-exhausted",
                    "sides": {
                        "A": {"name": "Avengers Mansion"},
                        "B": {"name": "Avengers Mansion (Used)"},
                    },
                    "exhausted": True,
                    "tokens": {},
                    "rotation": 180,
                },
            },
            "groupById": {
                "player1Play1": {
                    "stackIds": ["card-exhausted"],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Exhausted card (Side B) remains visible
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card["name"] == "Avengers Mansion (Used)"
    assert card["id"] == "uuid-exhausted"
    assert card["currentSide"] == "B"
    assert card["exhausted"] is True
    assert card["stackSize"] == 1


def test_simplify_marvel_state_hides_facedown_stacked_cards():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-a": {
                    "databaseId": "uuid-a",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "s_stack_card-a",
                    "sides": {"A": {"name": "Hero"}},
                    "exhausted": False,
                    "tokens": {},
                    "rotation": 180,
                },
                "card-b": {
                    "databaseId": "uuid-b",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "s_stack_card-a",
                    "sides": {"A": {"name": "Upgrade"}},
                    "exhausted": False,
                    "tokens": {},
                    "rotation": 180,
                },
            },
            "groupById": {
                "player1Play1": {
                    "stackIds": ["s_stack_card-a"],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Both cards facedown, shows HIDDEN with stack size 2, masks id details
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card["name"] == "HIDDEN"
    assert card["id"] == "Unknown"
    assert card["instanceId"] == "card-a"
    assert card["stackSize"] == 2


def test_simplify_marvel_state_masks_id_for_player_encounter_cards():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-player": {
                    "databaseId": "uuid-player",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-player",
                    "sides": {"A": {"name": "player"}},
                    "exhausted": False,
                    "tokens": {},
                },
            },
            "groupById": {
                "sharedVillain": {
                    "stackIds": ["card-player"],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Player card merged into HIDDEN since it has masked id
    assert len(result_dict["zones"]["sharedVillain"]) == 1
    card = result_dict["zones"]["sharedVillain"][0]
    assert card["name"] == "HIDDEN"
    assert card["id"] == "Unknown"
    assert card["instanceId"] == "card-player"
    assert card["stackSize"] == 1


def test_simplify_marvel_state_merges_unknown_cards_in_zone():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-facedown-1": {
                    "databaseId": "uuid-1",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-facedown-1",
                    "sides": {"A": {"name": "Villain"}},
                    "exhausted": False,
                    "tokens": {},
                    "rotation": 180,
                },
                "card-facedown-2": {
                    "databaseId": "uuid-2",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-facedown-2",
                    "sides": {"A": {"name": "Minion"}},
                    "exhausted": False,
                    "tokens": {},
                    "rotation": 180,
                },
                "card-visible": {
                    "databaseId": "uuid-visible",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-visible",
                    "sides": {"A": {"name": "Goblin"}},
                    "exhausted": False,
                    "tokens": {},
                },
            },
            "groupById": {
                "sharedVillain": {
                    "stackIds": ["card-facedown-1", "card-facedown-2", "card-visible"],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Two facedown cards merged into one HIDDEN entry
    assert len(result_dict["zones"]["sharedVillain"]) == 2
    hidden = [c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "HIDDEN"]
    visible = [
        c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "Goblin"
    ]
    assert len(hidden) == 1
    assert hidden[0]["id"] == "Unknown"
    assert hidden[0]["instanceId"] == "card-facedown-1"
    assert hidden[0]["stackSize"] == 2
    assert len(visible) == 1


def test_simplify_marvel_state_merges_mixed_unknown_cards():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-exhausted-1": {
                    "databaseId": "uuid-1",
                    "currentSide": "B",
                    "groupId": "sharedVillain",
                    "stackId": "card-exhausted-1",
                    "sides": {"A": {"name": "Villain"}, "B": {"name": "Villain Used"}},
                    "exhausted": True,
                    "tokens": {},
                    "rotation": 180,
                },
                "card-player-1": {
                    "databaseId": "uuid-player",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-player-1",
                    "sides": {"A": {"name": "player"}},
                    "exhausted": False,
                    "tokens": {},
                },
                "card-encounter-1": {
                    "databaseId": "uuid-encounter",
                    "currentSide": "A",
                    "groupId": "sharedVillain",
                    "stackId": "card-encounter-1",
                    "sides": {"A": {"name": "encounter"}},
                    "exhausted": False,
                    "tokens": {},
                },
            },
            "groupById": {
                "sharedVillain": {
                    "stackIds": [
                        "card-exhausted-1",
                        "card-player-1",
                        "card-encounter-1",
                    ],
                }
            },
        }
    }
    result = _simplify_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Exhausted card is visible, player/encounter cards merged into HIDDEN
    assert len(result_dict["zones"]["sharedVillain"]) == 2
    exhausted = [
        c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "Villain Used"
    ]
    hidden = [c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "HIDDEN"]
    assert len(exhausted) == 1
    assert exhausted[0]["currentSide"] == "B"
    assert exhausted[0]["exhausted"] is True
    assert len(hidden) == 1
    assert hidden[0]["stackSize"] == 2


async def test_get_game_state_simplified_200():
    session = mock_session()
    session.get_state = AsyncMock(
        return_value={
            "game": {
                "roundNumber": 1,
                "mode": "hero",
                "villainHitPoints": 0,
                "playerData": {},
                "cardById": {},
            }
        }
    )
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")
    assert response.status_code == 200
    body = response.json()
    # Simplified format has flat keys
    assert body["state"]["roundNumber"] == 1
    assert "game" not in body["state"]  # not nested under 'game'


async def test_get_game_state_raw_for_non_marvel():
    session = mock_session()
    session.plugin_name = "other-game"
    session.get_state = AsyncMock(return_value={"game": {"roundNumber": 1}})
    async with make_client(mock_manager(session)) as client:
        response = await client.get(f"/games/{SESSION_ID}/state")
    assert response.status_code == 200
    body = response.json()
    # Original nested structure preserved for non-Marvel
    assert body["state"]["game"]["roundNumber"] == 1
