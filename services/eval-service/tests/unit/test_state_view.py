from __future__ import annotations

import json

from eval_service.judge.state_view import project_state, render_state


def _raw_state(*, deltas_entries: int = 400) -> dict:
    """A raw DragnCards room state shaped like the recorded article.

    ``deltas`` is DragnCards' internal undo/replay log. It sorts BEFORE ``game``
    under canonical (sorted-key) JSON, which is why clipping the serialised state
    to a character budget used to yield a prompt made entirely of delta log.
    """
    return {
        "cachedTimeout": 3600000,
        "createdAt": "2026-06-29T14:48:37Z",
        "deltas": [
            {"cardById": {"filler": ["x" * 200]}} for _ in range(deltas_entries)
        ],
        "sockets": {"s1": "player1"},
        "playerInfo": {"player1": {}},
        "game": {
            "roundNumber": 2,
            "mode": "standard",
            "stepId": "1.1",
            "firstPlayer": "player1",
            "numPlayers": 1,
            "villainHitPoints": 14,
            # Plugin configuration a judge has no use for.
            "functions": {"f": ["x" * 500]},
            "automationActionLists": {"a": ["y" * 500]},
            "ruleById": {"r": {"z": "z" * 500}},
            "layout": {"regions": {"deep": "l" * 500}},
            "playerData": {
                "player1": {
                    "alias": "dev_user",
                    "hitPoints": 10,
                    "handSize": 6,
                    "layout": {"regions": {"deep": "p" * 500}},
                },
                "player2": {"alias": None, "hitPoints": 0, "handSize": 0},
            },
            "groupById": {"player1Hand": {"stackIds": ["s_backflip"]}},
            "cardById": {
                "backflip_1": {
                    "groupId": "player1Hand",
                    "stackId": "backflip_1",
                    "currentSide": "A",
                    "rotation": 0,
                    "exhausted": False,
                    "tokens": {"damage": 0, "threat": 0},
                    "sides": {
                        "A": {
                            "name": "Backflip",
                            "type": "Event",
                            "traits": "Defense,Skill",
                            "imageUrl": "/official/01.jpg",
                            "width": 1.0,
                        },
                        "B": {"name": "player"},
                    },
                },
                "rhino_1": {
                    "groupId": "sharedVillain",
                    "stackId": "rhino_1",
                    "currentSide": "A",
                    "rotation": 0,
                    "exhausted": False,
                    "tokens": {"damage": 8},
                    "sides": {
                        "A": {
                            "name": "Rhino",
                            "type": "Villain",
                            "stage": "I",
                            "traits": "Brute,Criminal",
                        }
                    },
                },
                # A deck card: shows the generic player back, so it is hidden.
                "secretplan_1": {
                    "groupId": "player1Deck",
                    "stackId": "secretplan_1",
                    "currentSide": "B",
                    "rotation": 0,
                    "exhausted": False,
                    "sides": {
                        "A": {"name": "Swinging Web Kick", "type": "Event"},
                        "B": {"name": "player"},
                    },
                },
                # A face-down staged encounter card (rotated, side A, not exhausted).
                "ambush_1": {
                    "groupId": "player1Engaged",
                    "stackId": "ambush_1",
                    "currentSide": "A",
                    "rotation": 90,
                    "exhausted": False,
                    "sides": {"A": {"name": "Ambushed!", "type": "Treachery"}},
                },
                # Buried under an attachment stack: described only as a stack size.
                "upgrade_under": {
                    "groupId": "player1Play2",
                    "stackId": "s_tracer_top",
                    "currentSide": "A",
                    "sides": {"A": {"name": "Buried Upgrade", "type": "Upgrade"}},
                },
                "s_tracer_top": {
                    "groupId": "player1Play2",
                    "stackId": "s_tracer_top",
                    "currentSide": "A",
                    "rotation": 0,
                    "exhausted": True,
                    "sides": {"A": {"name": "Spider-Tracer", "type": "Upgrade"}},
                },
            },
        },
    }


def test_projection_drops_the_delta_log_and_keeps_the_board():
    # The bug this guards: the recorded state's `deltas` log dominated the
    # serialised JSON and sorted ahead of `game`, so a character-clipped prompt
    # contained only delta log and no board at all.
    state = _raw_state()
    raw_chars = len(json.dumps(state, sort_keys=True, default=str))
    rendered = render_state(state, 20_000, label="prior")

    assert "deltas" not in rendered
    assert "automationActionLists" not in rendered
    assert "functions" not in rendered
    # The board a judge needs IS present.
    assert "Backflip" in rendered
    assert "Rhino" in rendered
    assert '"villainHitPoints": 14' in rendered
    assert '"roundNumber": 2' in rendered
    assert '"hitPoints": 10' in rendered
    # And it is a fraction of the recorded state.
    assert len(rendered) < raw_chars / 20


def test_projection_keeps_hidden_information_hidden():
    projected = project_state(_raw_state())
    zones = projected["zones"]
    rendered = json.dumps(projected, sort_keys=True)

    # Deck contents and face-down cards collapse to a count, never a name.
    assert zones["player1Deck"] == [{"name": "HIDDEN", "count": 1}]
    assert zones["player1Engaged"] == [{"name": "HIDDEN", "count": 1}]
    assert "Swinging Web Kick" not in rendered
    assert "Ambushed!" not in rendered


def test_projection_describes_a_card_the_way_the_agent_saw_it():
    zones = project_state(_raw_state())["zones"]
    assert zones["player1Hand"] == [
        {
            "instanceId": "backflip_1",
            "name": "Backflip",
            "type": "Event",
            "traits": "Defense,Skill",
        }
    ]
    # instanceId is retained so the judge can correlate the move's arguments.
    assert zones["sharedVillain"] == [
        {
            "instanceId": "rhino_1",
            "name": "Rhino",
            "type": "Villain",
            "stage": "I",
            "traits": "Brute,Criminal",
            "tokens": {"damage": 8},
        }
    ]
    # Only the top of a stack is described, with the stack's size.
    assert zones["player1Play2"] == [
        {
            "instanceId": "s_tracer_top",
            "name": "Spider-Tracer",
            "type": "Upgrade",
            "exhausted": True,
            "stackSize": 2,
        }
    ]
    assert "Buried Upgrade" not in json.dumps(zones)


def test_projection_omits_unoccupied_seats_and_zero_tokens():
    projected = project_state(_raw_state())
    assert list(projected["players"]) == ["player1"]
    assert "tokens" not in projected["zones"]["player1Hand"][0]


def test_step_description_matches_the_agents_vocabulary():
    assert project_state(_raw_state())["stepDescription"] == "Player Turn"


def test_unrecognised_state_shape_is_sent_as_recorded():
    # An already-simplified or future state shape must not be silently emptied.
    simplified = {"roundNumber": 3, "zones": {"player1Hand": ["a"]}}
    assert project_state(simplified) is None
    rendered = render_state(simplified, 20_000, label="prior")
    assert json.loads(rendered) == simplified


def test_projection_remains_bounded_by_the_char_cap(caplog):
    state = _raw_state(deltas_entries=10)
    with caplog.at_level("INFO"):
        rendered = render_state(state, 200, label="prior")
    assert "[truncated" in rendered
    assert len(rendered) < 400
    assert any("Truncated projected prior state" in r.message for r in caplog.records)


def test_missing_state_renders_as_null():
    assert render_state(None, 20_000, label="prior") == "null"
