"""Deterministic regressions for survival-aware Marvel race planning.

These tests model the normalized state contract and explicit lookup values. They do not
require a game engine, a live table, hidden encounter cards, or an LLM provider.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
STRATEGY_PATH = (
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "strategy.md"
)

RHINO_MULTI_STAGE_STATE: dict[str, Any] = {
    "playRound": 4,
    "phase": "player",
    "phaseLabel": "Player Turn",
    "mode": "in progress",
    "pendingSeats": ["player1"],
    "players": {"player1": {"hitPoints": 10}},
    "villainHitPoints": 19,
    "zones": {
        "sharedVillain": [{"name": "Rhino I", "tokens": {"damage": 0}}],
        "sharedVillainDeck": [{"name": "Rhino II", "tokens": {"damage": 0}}],
        "sharedMainScheme": [
            {"name": "The Break-In!", "tokens": {"threat": 4}}
        ],
        "player1Play1": [{"name": "Spider-Man", "tokens": {"damage": 0}}],
    },
}

LOW_HEALTH_STATE: dict[str, Any] = {
    "playRound": 4,
    "phase": "player",
    "phaseLabel": "Player Turn",
    "mode": "in progress",
    "pendingSeats": ["player1"],
    "players": {"player1": {"hitPoints": 10}, "player2": {"hitPoints": 12}},
    "villainHitPoints": 19,
    "zones": {
        "sharedVillain": [{"name": "Rhino I", "tokens": {"damage": 6}}],
        "sharedMainScheme": [
            {"name": "The Break-In!", "tokens": {"threat": 8}}
        ],
        "player1Play1": [{"name": "Spider-Man", "tokens": {"damage": 8}}],
        "player1Engaged": [{"name": "Hydra Soldier", "tokens": {"damage": 0}}],
        "player2Play1": [{"name": "Captain Marvel", "tokens": {"damage": 1}}],
    },
}


def _strategy() -> str:
    return STRATEGY_PATH.read_text(encoding="utf-8")


def _full_villain_damage(
    state: dict[str, Any], stage_hit_points: dict[str, int] | None
) -> int | None:
    """Calculate the complete path only when every stage has an explicit HP lookup."""
    if state.get("mode") in {"win", "loss"} or stage_hit_points is None:
        return None
    villain = state.get("zones", {}).get("sharedVillain")
    if not isinstance(villain, list) or len(villain) != 1:
        return None
    active = villain[0]
    if not isinstance(active, dict) or not isinstance(active.get("name"), str):
        return None
    current_total = state.get("villainHitPoints")
    damage = active.get("tokens", {}).get("damage")
    if not _is_int(current_total) or not _is_int(damage):
        return None
    current_remaining = current_total - damage
    later = state.get("zones", {}).get("sharedVillainDeck")
    if not isinstance(later, list):
        return None
    later_remaining: list[int] = []
    for card in later:
        if not isinstance(card, dict) or card.get("name") == "HIDDEN":
            return None
        value = stage_hit_points.get(card.get("name"))
        if not _is_int(value):
            return None
        later_remaining.append(value)
    return current_remaining + sum(later_remaining)


def _remaining_hero_hp(state: dict[str, Any], seat: str) -> int | None:
    players = state.get("players", {})
    zones = state.get("zones", {})
    player = players.get(seat)
    identity_zone = zones.get(f"{seat}Play1")
    if not isinstance(player, dict) or not isinstance(identity_zone, list):
        return None
    if len(identity_zone) != 1 or not isinstance(identity_zone[0], dict):
        return None
    damage = identity_zone[0].get("tokens", {}).get("damage")
    maximum = player.get("hitPoints")
    if not _is_int(maximum) or not _is_int(damage):
        return None
    return maximum - damage


def _survival_outweighs_race(
    state: dict[str, Any],
    *,
    seat: str,
    incoming_damage: int,
    full_path_damage: int,
    credible_damage_per_round: int,
    survival_window_rounds: int,
) -> bool:
    """Use explicit loss and race windows for the low-health regression fixture."""
    remaining = _remaining_hero_hp(state, seat)
    if (
        remaining is None
        or remaining <= 0
        or not _is_int(incoming_damage)
        or not _is_int(full_path_damage)
        or credible_damage_per_round <= 0
    ):
        return False
    expected_team_loss = int(incoming_damage >= remaining)
    race_rounds = full_path_damage / credible_damage_per_round
    return expected_team_loss > 0 and race_rounds > survival_window_rounds


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def test_current_stage_hp_is_not_the_full_rhino_victory_path() -> None:
    strategy = _strategy()

    current_only = RHINO_MULTI_STAGE_STATE["villainHitPoints"] - RHINO_MULTI_STAGE_STATE[
        "zones"
    ]["sharedVillain"][0]["tokens"]["damage"]
    complete_path = _full_villain_damage(
        RHINO_MULTI_STAGE_STATE, {"Rhino II": 15}
    )

    assert current_only == 19
    assert complete_path == 34
    assert complete_path != current_only
    assert "villainHitPoints` is the total for the **current stage only**" in strategy
    assert "Rhino I at an authoritative 19 current-stage HP" in strategy
    assert "the known path is `19 + 15 = 34`" in strategy
    assert "must not stop after defeating Rhino I" in strategy


def test_hidden_later_stage_refuses_an_exact_victory_distance() -> None:
    strategy = " ".join(_strategy().lower().split())
    hidden_state = {
        **RHINO_MULTI_STAGE_STATE,
        "zones": {
            **RHINO_MULTI_STAGE_STATE["zones"],
            "sharedVillainDeck": [{"name": "HIDDEN", "stackSize": 1}],
        },
    }

    assert _full_villain_damage(hidden_state, {"Rhino II": 15}) is None
    assert "later-stage requirement as unknown" in strategy
    assert "refuse to call the full victory distance or race safe" in strategy


def test_low_health_hero_outweighs_a_race_that_misses_the_survival_window() -> None:
    strategy = " ".join(_strategy().lower().split())
    remaining = _remaining_hero_hp(LOW_HEALTH_STATE, "player1")

    assert remaining == 2
    assert remaining > 0
    assert _survival_outweighs_race(
        LOW_HEALTH_STATE,
        seat="player1",
        incoming_damage=3,
        full_path_damage=34,
        credible_damage_per_round=8,
        survival_window_rounds=2,
    )
    assert "positive low hp is a major team-risk input, not automatic game over" in strategy
    assert "the expected team loss outweighs the race value" in strategy
    assert "switch to survival or the highest-value threat-control line" in strategy
    assert "game loss occurs only when all players are eliminated" in strategy


def test_terminal_mode_precedes_stale_damage_and_survival_reports() -> None:
    strategy = " ".join(_strategy().lower().split())
    terminal = {**LOW_HEALTH_STATE, "mode": "loss"}

    assert _full_villain_damage(terminal, {"Rhino II": 15}) is None
    assert "mode=win` or" in strategy
    assert "mode=loss` is terminal" in strategy
    assert "takes precedence over a stale damage or threat report" in strategy


@pytest.mark.parametrize("field", ["villainHitPoints", "players", "zones"])
def test_required_state_facts_are_not_replaced_with_zero(field: str) -> None:
    strategy = " ".join(_strategy().lower().split())
    incomplete = dict(RHINO_MULTI_STAGE_STATE)
    incomplete.pop(field)

    assert "do not" in strategy
    assert "unknown" in strategy
    if field == "villainHitPoints":
        assert _full_villain_damage(incomplete, {"Rhino II": 15}) is None
    elif field == "players":
        assert _remaining_hero_hp(incomplete, "player1") is None
    else:
        assert _full_villain_damage(incomplete, {"Rhino II": 15}) is None
