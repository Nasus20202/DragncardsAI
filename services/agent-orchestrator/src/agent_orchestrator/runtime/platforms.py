"""Platform vocabulary shared by the agent runtime.

The game-service owns transport and state normalisation. The orchestrator only
needs the two stable slugs and the small part of the move surface that matters
to its seat and turn guards.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PLATFORM_DRAGNCARDS = "dragncards"
PLATFORM_MARVEL_LCG = "marvel-lcg"
DEFAULT_PLATFORM = PLATFORM_DRAGNCARDS
SUPPORTED_PLATFORMS = frozenset({PLATFORM_DRAGNCARDS, PLATFORM_MARVEL_LCG})


@dataclass(frozen=True)
class PlatformToolSets:
    """Turn-sensitive tools exposed by one platform."""

    phase_advancing: frozenset[str]
    seat_actions: frozenset[str]


DRAGNCARDS_TOOL_SETS = PlatformToolSets(
    phase_advancing=frozenset(
        {"next_step", "prev_step", "player_end_phase", "villain_end_phase"}
    ),
    seat_actions=frozenset(
        {
            "draw_card",
            "move_card",
            "set_card_property",
            "exhaust_card",
            "ready_card",
            "flip_card",
            "deal_encounter",
            "draw_boost",
            "shuffle_into_deck",
            "zero_tokens",
            "shadows_of_the_past",
            "villain_encounter_phase",
            "multiple_double_sided_villains",
            "discard_minion",
            "discard_side_scheme",
            "modify_tokens",
        }
    ),
)

# marvel-lcg advances turns as part of the engine-validated option it accepts.
# There is deliberately no phase-advancing call here.
MARVEL_LCG_TOOL_SETS = PlatformToolSets(
    phase_advancing=frozenset(),
    seat_actions=frozenset({"choose_game_option"}),
)

PLATFORM_TOOL_SETS = {
    PLATFORM_DRAGNCARDS: DRAGNCARDS_TOOL_SETS,
    PLATFORM_MARVEL_LCG: MARVEL_LCG_TOOL_SETS,
}


def normalize_platform(value: Any) -> str:
    """Return a supported platform slug, defaulting old sessions to DragnCards."""

    return value if value in SUPPORTED_PLATFORMS else DEFAULT_PLATFORM


def platform_tool_sets(platform: Any) -> PlatformToolSets:
    """Resolve the turn-sensitive tool sets for a session platform."""

    return PLATFORM_TOOL_SETS[normalize_platform(platform)]


def session_platform(session: Any) -> str:
    """Read a session's platform from either a column or legacy metadata."""

    value = getattr(session, "platform", None)
    if value is None:
        metadata = getattr(session, "metadata_json", None) or {}
        value = metadata.get("platform")
    return normalize_platform(value)
