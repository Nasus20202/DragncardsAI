"""Deterministic regressions for the Marvel player strategy reference.

These tests intentionally exercise the normalized state vocabulary as data and the
strategy reference as the executable contract. They do not require a running engine.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
STRATEGY_PATH = (
    REPO_ROOT / "skills" / "marvel-champions-play" / "resources" / "strategy.md"
)

RHINO_RISK_STATE: dict[str, Any] = {
    "playRound": 3,
    "phase": "player",
    "zones": {
        "sharedMainScheme": [
            {
                "name": "The Break-In!",
                "tokens": {"threat": 9, "target_threat": 14},
            }
        ],
        "sharedSideSchemes": [
            {
                "name": "Crowd Control",
                "tokens": {"threat": 3, "crisis": 1},
            },
            {
                "name": "Breakin' & Takin'",
                "tokens": {"threat": 4, "hazard": 1},
            },
            {
                "name": "Highway Robbery",
                "tokens": {"threat": 5, "acceleration": 1},
            },
            {
                "name": "Resource Squeeze",
                "tokens": {"threat": 2, "hand": 1, "resource": 1},
            },
        ],
    },
}


def _strategy() -> str:
    return STRATEGY_PATH.read_text(encoding="utf-8")


def _numeric(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _effect_priority(card: dict[str, Any], *, main_control_needed: bool) -> tuple[int, ...]:
    """Mirror the reference's deterministic effect ordering for regression data."""
    tokens = card["tokens"]
    crisis_blocker = int(main_control_needed and _numeric(tokens.get("crisis")) > 0)
    acceleration = _numeric(tokens.get("acceleration"))
    hazard = _numeric(tokens.get("hazard"))
    denial = int(
        _numeric(tokens.get("hand")) > 0 or _numeric(tokens.get("resource")) > 0
    )
    threat = _numeric(tokens.get("threat"))
    return crisis_blocker, acceleration, hazard, denial, threat


def _ranked_side_scheme_names(state: dict[str, Any]) -> list[str]:
    side_schemes = state["zones"]["sharedSideSchemes"]
    return [
        card["name"]
        for card in sorted(
            side_schemes,
            key=lambda card: _effect_priority(card, main_control_needed=True),
            reverse=True,
        )
    ]


def _minimum_next_threat(
    state: dict[str, Any],
    *,
    base_placement: int | None,
    main_acceleration: int | None,
    alter_ego_scheme: list[int] | None,
) -> int | None:
    """Calculate the explicit lower bound, refusing incomplete required inputs."""
    main = state["zones"]["sharedMainScheme"][0]
    current = _numeric(main["tokens"].get("threat"))
    if (
        base_placement is None
        or main_acceleration is None
        or alter_ego_scheme is None
        or any(not isinstance(value, int) or isinstance(value, bool) for value in alter_ego_scheme)
    ):
        return None
    return current + base_placement + main_acceleration + sum(alter_ego_scheme)


def test_multiple_active_side_schemes_keep_distinct_effect_priorities() -> None:
    strategy = _strategy()
    side_schemes = RHINO_RISK_STATE["zones"]["sharedSideSchemes"]

    assert len(side_schemes) == 4
    assert _ranked_side_scheme_names(RHINO_RISK_STATE) == [
        "Crowd Control",
        "Highway Robbery",
        "Breakin' & Takin'",
        "Resource Squeeze",
    ]
    for field in (
        "zones.sharedSideSchemes",
        "tokens.crisis",
        "tokens.hazard",
        "tokens.acceleration",
        "tokens.hand",
        "tokens.resource",
        "tokens.threat",
    ):
        assert field in strategy

    # The worked normalized checkpoint must preserve the same named ordering.
    table_start = strategy.index("| Rank in the 9/14 risk line |")
    table_end = strategy.index("This ordering is conditional", table_start)
    table = strategy[table_start:table_end]
    positions = [table.index(name) for name in ("Crowd Control", "Highway Robbery", "Breakin' & Takin'")]
    assert positions == sorted(positions)


def test_crisis_blocks_main_scheme_threat_removal() -> None:
    strategy = _strategy().lower()
    crisis = next(
        card
        for card in RHINO_RISK_STATE["zones"]["sharedSideSchemes"]
        if card["name"] == "Crowd Control"
    )

    assert crisis["tokens"]["crisis"] == 1
    assert "player cards cannot remove threat from the **main scheme**" in strategy
    assert "do not spend a player-card thwart on the main scheme while crisis remains" in strategy
    assert "side-scheme threat remains a legal target" in strategy


def test_minimum_projection_hits_9_of_14_checkpoint() -> None:
    strategy = _strategy()
    main = RHINO_RISK_STATE["zones"]["sharedMainScheme"][0]

    assert main["tokens"]["threat"] == 9
    assert main["tokens"]["target_threat"] == 14
    assert _minimum_next_threat(
        RHINO_RISK_STATE,
        base_placement=2,
        main_acceleration=1,
        alter_ego_scheme=[2],
    ) == 14
    assert "9 + 2 + 1 + 2 = 14" in strategy
    assert "WARNING: minimum next-villain-phase threat reaches 14/14" in strategy
    assert "before reporting the player phase complete" in strategy


@pytest.mark.parametrize(
    ("base_placement", "main_acceleration", "alter_ego_scheme"),
    [
        (None, 1, [2]),
        (2, None, [2]),
        (2, 1, None),
    ],
)
def test_unknown_required_gain_refuses_an_exact_clock(
    base_placement: int | None,
    main_acceleration: int | None,
    alter_ego_scheme: list[int] | None,
) -> None:
    strategy = " ".join(_strategy().lower().split())

    assert _minimum_next_threat(
        RHINO_RISK_STATE,
        base_placement=base_placement,
        main_acceleration=main_acceleration,
        alter_ego_scheme=alter_ego_scheme,
    ) is None
    assert "state the missing value and refuse to claim an exact minimum" in strategy
    assert "refuse to claim an exact clock" in strategy
    assert "do not silently use one threat per player" in strategy


def test_unknown_target_is_not_called_safe_and_plans_recompute() -> None:
    strategy = " ".join(_strategy().lower().split())
    missing_target = dict(RHINO_RISK_STATE["zones"]["sharedMainScheme"][0])
    missing_target["tokens"] = {"threat": 9}

    assert "target_threat" not in missing_target["tokens"]
    assert "never infer a target from a familiar scenario" in strategy
    assert "if the target, base" in strategy
    assert "recompute after clearing or adding a side scheme" in strategy
    assert "replan the damage-versus-threat choice" in strategy


def test_deferred_side_scheme_requires_current_state_reason() -> None:
    strategy = _strategy()

    assert "Deferred: <name> — current threat=<value>; effects=<non-zero indicators>." in strategy
    assert "Reason: <current-state fact>, so <named higher-ranked line> is required first." in strategy
    assert "Deferred: Breakin' & Takin' — current threat=4; effects=hazard=1." in strategy
    assert "current thwart=2 is reserved to clear Crowd Control's crisis=1 blocker" in strategy
    assert "never write only “handle it later,” “not important,”" in strategy.lower()
