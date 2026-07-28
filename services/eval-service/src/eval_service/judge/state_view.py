"""Project a recorded DragnCards state down to what a judge needs to rule.

``game-service`` records the RAW DragnCards room state on every ``game_state``
event. Measured on real recorded games that payload is ~450-470 KB, of which
~225 KB is ``deltas`` (DragnCards' internal undo/replay log) and most of the rest
is plugin configuration: layouts, automation action lists, rule definitions,
image URLs, and both faces of every card definition including artwork geometry.

Serialising that and clipping it to a character budget is the worst of both
worlds. ``deltas`` sorts before ``game`` under canonical (sorted-key) JSON, so a
20,000-character prefix of a 470,000-character state is *entirely* delta log: the
judge was paying ~13,700 prompt tokens per move to see no board at all.

This module builds a small structured projection instead, mirroring the
`SimplifiedGameState` shape the game-service already serves to the playing agent
(``roundNumber``, ``mode``, ``stepId``, per-player hit points / hand size, and
per-zone card lists). The judge therefore sees the same view of the table the
agent saw when it decided, which is the right basis for grading that decision.

Hidden information stays hidden: face-down cards and cards showing a generic
``player``/``encounter`` back collapse to a ``HIDDEN`` entry with a count, so deck
contents never leak into a prompt whose rubric says not to assume hidden
information (and 60+ deck cards stop being serialised).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Human-readable step descriptions, mirroring the game-service's own mapping so
# the judge reads the same phase vocabulary the playing agent was given.
STEP_DESCRIPTIONS: dict[str, str] = {
    "0.0": "Beginning of Round",
    "0.1": "End of Round",
    "1.1": "Player Turn",
    "1.2": "End of Player Phase",
    "2.1": "Place threat on the main scheme.",
    "2.2": "The villain activates once per player, along with any eligible minions",
    "2.3": "Deal one encounter card to each player.",
    "2.4": "Reveal encounter cards.",
    "2.5": "Pass the first player token and end the round.",
}

# Card backs DragnCards uses for a face-down card; never a real card name.
_GENERIC_BACKS = ("player", "encounter")

# Top-level game fields worth carrying: scalar context a judge reasons about.
_GAME_SCALARS = (
    "roundNumber",
    "mode",
    "stepId",
    "firstPlayer",
    "numPlayers",
    "villainHitPoints",
)


def canonical_json(value: Any) -> str:
    """Serialize deterministically, falling back to ``repr`` on odd types."""
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError, ValueError:
        return repr(value)


def is_raw_dragncards_state(state: Any) -> bool:
    """Whether ``state`` is the raw DragnCards room state this module projects."""
    if not isinstance(state, dict):
        return False
    game = state.get("game")
    return isinstance(game, dict) and isinstance(game.get("cardById"), dict)


def project_state(state: Any) -> dict[str, Any] | None:
    """Project a raw DragnCards room state to the judge's view.

    Returns None when ``state`` is not the raw shape (an already-simplified state,
    a test fixture, or a future shape), so the caller can fall back to sending the
    state as recorded rather than silently dropping content it does not
    understand.
    """
    if not is_raw_dragncards_state(state):
        return None
    game = state["game"]

    projected: dict[str, Any] = {
        key: game[key] for key in _GAME_SCALARS if game.get(key) is not None
    }
    step_id = game.get("stepId")
    description = STEP_DESCRIPTIONS.get(str(step_id)) if step_id is not None else None
    if description:
        projected["stepDescription"] = description

    players = _project_players(game.get("playerData"))
    if players:
        projected["players"] = players
    projected["zones"] = _project_zones(game)
    return projected


def _project_players(player_data: Any) -> dict[str, Any]:
    """Per-seat hit points and hand size for seats that are actually occupied."""
    if not isinstance(player_data, dict):
        return {}
    out: dict[str, Any] = {}
    for player_id, info in player_data.items():
        if not isinstance(info, dict) or info.get("alias") is None:
            continue
        out[str(player_id)] = {
            "hitPoints": info.get("hitPoints", 0),
            "handSize": info.get("handSize", 0),
        }
    return out


def _project_zones(game: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group the visible top-of-stack cards by zone, collapsing hidden ones.

    Only the top card of a stack is described (an attachment stack is reported
    with its size), matching how the playing agent sees the table.
    """
    cards = game.get("cardById")
    if not isinstance(cards, dict):
        return {}

    stack_sizes: dict[str, int] = {}
    for card in cards.values():
        if not isinstance(card, dict):
            continue
        stack_id = card.get("stackId")
        if stack_id:
            stack_sizes[stack_id] = stack_sizes.get(stack_id, 0) + 1

    zones: dict[str, list[dict[str, Any]]] = {}
    hidden_counts: dict[str, int] = {}

    for card_id, card in cards.items():
        if not isinstance(card, dict):
            continue
        zone = card.get("groupId")
        if not zone:
            continue
        stack_id = card.get("stackId")
        # Skip cards buried under the top of their stack.
        if stack_id and stack_id != card_id and not stack_id.endswith(f"_{card_id}"):
            continue
        size = stack_sizes.get(stack_id, 1) if stack_id else 1

        side_name = card.get("currentSide", "A")
        sides = card.get("sides")
        side = sides.get(side_name) if isinstance(sides, dict) else None
        side = side if isinstance(side, dict) else {}
        name = side.get("name") or "Unknown"
        exhausted = bool(card.get("exhausted"))
        face_down = card.get("rotation", 0) != 0 and side_name == "A" and not exhausted

        if name in _GENERIC_BACKS or face_down:
            hidden_counts[str(zone)] = hidden_counts.get(str(zone), 0) + size
            continue

        entry: dict[str, Any] = {"instanceId": str(card_id), "name": name}
        for source_key, out_key in (
            ("type", "type"),
            ("stage", "stage"),
            ("traits", "traits"),
        ):
            value = side.get(source_key)
            if value:
                entry[out_key] = value
        tokens = card.get("tokens")
        if isinstance(tokens, dict):
            live = {k: v for k, v in tokens.items() if v}
            if live:
                entry["tokens"] = live
        if exhausted:
            entry["exhausted"] = True
        if side_name != "A":
            entry["side"] = side_name
        if size > 1:
            entry["stackSize"] = size
        zones.setdefault(str(zone), []).append(entry)

    for zone, count in hidden_counts.items():
        zones.setdefault(zone, []).append({"name": "HIDDEN", "count": count})
    return zones


def render_state(value: Any, max_chars: int, *, label: str) -> str:
    """Render a recorded state for a judge prompt, bounded by ``max_chars``.

    Projects the raw DragnCards shape first (a ~180x reduction on real games) and
    only then applies the character bound as a backstop. States in an unknown
    shape are serialised as recorded, preserving the previous behaviour. Any
    truncation is marked in the text and logged so it stays observable.
    """
    projected = project_state(value)
    if projected is not None:
        rendered = canonical_json(projected)
        kind = "projected"
    else:
        rendered = canonical_json(value)
        kind = "raw"

    if max_chars > 0 and len(rendered) > max_chars:
        logger.info(
            "Truncated %s %s state JSON from %d to %d chars for judge input",
            kind,
            label,
            len(rendered),
            max_chars,
        )
        return (
            rendered[:max_chars]
            + f"\n...[truncated {len(rendered) - max_chars} chars of {label} state]"
        )
    return rendered
