from __future__ import annotations

from unittest.mock import AsyncMock

from game_service.logic.normalisers import (
    _get_step_description,
    simplify_dragncards_marvel_state,
)
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
    assert body["state"]["playRound"] == 2
    assert "roundNumber" not in body["state"]
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
    assert response.json()["state"]["playRound"] == 3
    assert "roundNumber" not in response.json()["state"]


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
            "stepId": "1.1",
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
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    assert result_dict["playRound"] == 4
    assert "roundNumber" not in result_dict
    assert result_dict["mode"] == "villain"
    assert result_dict["villainHitPoints"] == 8
    assert result_dict["stepId"] == "1.1"
    assert result_dict["stepDescription"] == "Player Turn"
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
    # Compact: currentSide="A" and exhausted=False are the schema defaults
    # and are therefore omitted from the emitted card.
    assert "currentSide" not in card
    assert "exhausted" not in card
    assert card["tokens"] == {"damage": 1}
    assert card["stackSize"] == 1


def test_get_step_description_known_steps():
    assert _get_step_description("0.0") == "Beginning of Round"
    assert _get_step_description("0.1") == "End of Round"
    assert _get_step_description("1.1") == "Player Turn"
    assert _get_step_description("1.2") == "End of Player Phase"
    assert _get_step_description("2.1") == "Place threat on the main scheme."
    assert (
        _get_step_description("2.2")
        == "The villain activates once per player, along with any eligible minions"
    )
    assert _get_step_description("2.3") == "Deal one encounter card to each player."
    assert _get_step_description("2.4") == "Reveal encounter cards."
    assert (
        _get_step_description("2.5") == "Pass the first player token and end the round."
    )


def test_get_step_description_unknown_step():
    assert _get_step_description("9.9") is None
    assert _get_step_description(None) is None


def test_simplify_marvel_state_without_step_id():
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {},
        }
    }
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    assert result_dict["stepId"] is None
    assert result_dict["stepDescription"] is None


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
    result = simplify_dragncards_marvel_state(raw)
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
    result = simplify_dragncards_marvel_state(raw)
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
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Facedown card (Side A with rotation) shows only stack size with name HIDDEN
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card["name"] == "HIDDEN"
    assert card == {"name": "HIDDEN", "stackSize": 1}


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
    result = simplify_dragncards_marvel_state(raw)
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
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Both cards facedown, shows HIDDEN with stack size 2
    assert len(result_dict["zones"]["player1Play1"]) == 1
    card = result_dict["zones"]["player1Play1"][0]
    assert card == {"name": "HIDDEN", "stackSize": 2}


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
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Player card merged into HIDDEN
    assert len(result_dict["zones"]["sharedVillain"]) == 1
    card = result_dict["zones"]["sharedVillain"][0]
    assert card == {"name": "HIDDEN", "stackSize": 1}


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
    result = simplify_dragncards_marvel_state(raw)
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result

    # Two facedown cards merged into one HIDDEN entry
    assert len(result_dict["zones"]["sharedVillain"]) == 2
    hidden = [c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "HIDDEN"]
    visible = [
        c for c in result_dict["zones"]["sharedVillain"] if c["name"] == "Goblin"
    ]
    assert len(hidden) == 1
    assert hidden[0] == {"name": "HIDDEN", "stackSize": 2}
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
    result = simplify_dragncards_marvel_state(raw)
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
    assert body["state"]["playRound"] == 2
    assert "roundNumber" not in body["state"]
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


def test_simplify_marvel_state_hides_default_values():
    """A face-up unexhausted card with no tokens must emit only the four
    always-present fields, so a typical mid-game state fits the MCP
    WebSocket transport limit (DRA-43)."""
    raw = {
        "game": {
            "roundNumber": 2,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-quiet": {
                    "databaseId": "uuid-quiet",
                    "currentSide": "A",
                    "groupId": "player1Hand",
                    "stackId": "card-quiet",
                    "sides": {"A": {"name": "Spider-Man"}},
                    "exhausted": False,
                    "tokens": {
                        "damage": 0,
                        "threat": 0,
                        "generic": 0,
                        "acceleration": 0,
                        "confused": 0,
                        "stunned": 0,
                        "tough": 0,
                    },
                },
            },
        }
    }
    result = simplify_dragncards_marvel_state(raw)

    card = result["zones"]["player1Hand"][0]
    # Only the four always-present fields are emitted.
    assert set(card.keys()) == {"id", "instanceId", "name", "stackSize"}
    assert card["id"] == "uuid-quiet"
    assert card["instanceId"] == "card-quiet"
    assert card["name"] == "Spider-Man"
    assert card["stackSize"] == 1


def test_simplify_marvel_state_keeps_non_default_token_counters():
    """A card with one non-zero token counter emits only that counter, not
    the full seven-key dict."""
    raw = {
        "game": {
            "roundNumber": 2,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-damaged": {
                    "databaseId": "uuid-damaged",
                    "currentSide": "A",
                    "groupId": "player1Play1",
                    "stackId": "card-damaged",
                    "sides": {"A": {"name": "Iron Man"}},
                    "exhausted": False,
                    "tokens": {
                        "damage": 3,
                        "threat": 0,
                        "generic": 0,
                        "acceleration": 0,
                        "confused": 0,
                        "stunned": 0,
                        "tough": 0,
                    },
                },
            },
        }
    }
    result = simplify_dragncards_marvel_state(raw)

    card = result["zones"]["player1Play1"][0]
    assert card["tokens"] == {"damage": 3}
    # Default-valued fields stay omitted.
    assert "currentSide" not in card
    assert "exhausted" not in card


def test_simplify_marvel_state_hidden_entry_has_only_name_and_stack_size():
    """HIDDEN entries collapse to {name, stackSize} — the agent never needs
    to target face-down cards, and the count is the only thing it acts on."""
    raw = {
        "game": {
            "roundNumber": 1,
            "mode": "hero",
            "villainHitPoints": 0,
            "playerData": {},
            "cardById": {
                "card-facedown": {
                    "databaseId": "uuid-1",
                    "currentSide": "A",
                    "groupId": "sharedEncounterDeck",
                    "stackId": "card-facedown",
                    "sides": {"A": {"name": "Mysterio"}},
                    "exhausted": False,
                    "rotation": 180,
                },
            },
        }
    }
    result = simplify_dragncards_marvel_state(raw)

    hidden = result["zones"]["sharedEncounterDeck"][0]
    assert hidden == {"name": "HIDDEN", "stackSize": 1}


def test_simplify_marvel_state_payload_fits_mcp_limit():
    """Regression for DRA-43: a 4-player table with a full encounter set
    must produce a JSON payload that fits the 1,048,576-byte MCP WebSocket
    message size limit. The compact format must keep the body well under
    a quarter of that limit so the LLM can keep calling get_game_state
    mid-round without bouncing off the cap.
    """
    import json

    zones_layout = [
        ("player1Hand", 5, False),
        ("player1Deck", 30, True),  # face-down
        ("player1Discard", 4, False),
        ("player1Play1", 1, False),
        ("player1Play2", 1, False),
        ("player1Play3", 1, False),
        ("player1Play4", 1, False),
        ("player1Engaged", 1, False),
        ("player2Hand", 5, False),
        ("player2Deck", 30, True),
        ("player2Discard", 4, False),
        ("player2Play1", 1, False),
        ("player2Play2", 1, False),
        ("player2Play3", 1, False),
        ("player2Play4", 1, False),
        ("player2Engaged", 1, False),
        ("player3Hand", 5, False),
        ("player3Deck", 30, True),
        ("player3Discard", 4, False),
        ("player3Play1", 1, False),
        ("player3Play2", 1, False),
        ("player3Play3", 1, False),
        ("player3Play4", 1, False),
        ("player3Engaged", 1, False),
        ("player4Hand", 5, False),
        ("player4Deck", 30, True),
        ("player4Discard", 4, False),
        ("player4Play1", 1, False),
        ("player4Play2", 1, False),
        ("player4Play3", 1, False),
        ("player4Play4", 1, False),
        ("player4Engaged", 1, False),
        ("sharedVillain", 1, False),
        ("sharedVillainDeck", 4, True),
        ("sharedMainScheme", 1, False),
        ("sharedMainSchemeDeck", 3, True),
        ("sharedEncounterDeck", 8, True),
        ("sharedEncounterDiscard", 3, False),
        ("sharedEncounter2Deck", 3, True),
        ("sharedEncounter2Discard", 1, False),
        ("sharedEncounter3Deck", 3, True),
        ("sharedEncounter3Discard", 1, False),
    ]
    card_by_id: dict = {}
    group_by_id: dict = {}
    card_index = 0
    for zone_id, count, face_down in zones_layout:
        stack_ids = []
        for i in range(count):
            card_id = f"card-{zone_id}-{i}"
            stack_ids.append(card_id)
            card_by_id[card_id] = {
                "databaseId": f"uuid-{card_index}",
                "currentSide": "A",
                "groupId": zone_id,
                "stackId": card_id,
                "sides": {"A": {"name": f"Card {card_index}"}},
                "exhausted": False,
                "tokens": {
                    "damage": 0,
                    "threat": 0,
                    "generic": 0,
                    "acceleration": 0,
                    "confused": 0,
                    "stunned": 0,
                    "tough": 0,
                },
            }
            if face_down:
                card_by_id[card_id]["rotation"] = 180
            card_index += 1
        group_by_id[zone_id] = {"stackIds": stack_ids}

    raw = {
        "game": {
            "roundNumber": 2,
            "mode": "hero",
            "villainHitPoints": 30,
            "playerData": {
                f"player{n}": {
                    "alias": f"Hero {n}",
                    "hitPoints": 12,
                    "handSize": 5,
                }
                for n in range(1, 5)
            },
            "cardById": card_by_id,
            "groupById": group_by_id,
        }
    }

    result = simplify_dragncards_marvel_state(raw)
    payload = json.dumps(result, separators=(",", ":")).encode()
    # Compact format must keep the body well under 1/4 of the 1 MiB limit
    # so even larger custom-content tables stay well under the cap.
    assert len(payload) < 256_000, (
        f"Simplified state payload is {len(payload)} bytes, "
        f"exceeds the 256_000-byte soft cap (DRA-43)"
    )

    # And the structural rules hold across the whole payload.
    for zone_id, cards in result["zones"].items():
        for card in cards:
            if card.get("name") == "HIDDEN":
                assert set(card.keys()) == {
                    "name",
                    "stackSize",
                }, f"HIDDEN entry in {zone_id} leaked extra fields: {card}"
            else:
                # Visible cards only carry the four always-present fields
                # plus non-default currentSide / exhausted / tokens.
                allowed = {
                    "id",
                    "instanceId",
                    "name",
                    "stackSize",
                    "currentSide",
                    "exhausted",
                    "tokens",
                }
                assert set(card.keys()).issubset(allowed), (
                    f"Visible card in {zone_id} emitted unexpected fields: "
                    f"{set(card.keys()) - allowed}"
                )
                if "tokens" in card:
                    assert all(
                        value for value in card["tokens"].values()
                    ), f"Visible card in {zone_id} has a zero token: {card}"
