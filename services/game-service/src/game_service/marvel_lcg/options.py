"""Neutral option and prompt projections for marvel-lcg."""

from __future__ import annotations

import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field


class OptionTargetRange(BaseModel):
    min: int = Field(ge=0)
    max: int = Field(ge=0)

    def valid_count(self, count: int) -> bool:
        return self.min <= count <= self.max


class ResolvedTarget(BaseModel):
    id: str
    name: str = "HIDDEN"
    card_type: str = "unknown"
    type: str = "unknown"
    resolved: bool = True
    hidden: bool = False


class GameOption(BaseModel):
    """An option with all target identifiers made understandable to an agent."""

    model_config = ConfigDict(extra="allow")

    id: int | str
    name: str
    bind_id: str | None = None
    bound_seat: str | None = None
    targets: list[ResolvedTarget] = Field(default_factory=list)
    target_num_range: OptionTargetRange
    target_payment: Any = None
    select_rule: Any = None
    required_target_traits: Any = None
    failure_reason: str | None = None
    search: bool = False


class GameOptions(BaseModel):
    """The platform-neutral pending decision returned to callers."""

    session_id: str | None = None
    platform: Literal["marvel-lcg"] = "marvel-lcg"
    move_surface: Literal["enumerated_options"] = "enumerated_options"
    prompt_id: str | None = None
    prompt_version: int | None = None
    player_n: str
    asked_seats: list[str] = Field(default_factory=list)
    prompt: str = ""
    event_name: str | None = None
    ability_type: str | None = None
    can_decline: bool = False
    options: list[GameOption] = Field(default_factory=list)


def normalise_prompt(text: Any) -> str:
    """Remove graphical decoration without changing the prompt's words."""
    value = "" if text is None else str(text)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:[-–—•·]+\s*)+", "", value)
    value = re.sub(r"(?:\s*[-–—•·]+)+$", "", value)
    return value.strip()


def option_id(value: Any) -> int | str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, str)):
        return value
    return str(value)


def _id_key(value: Any) -> str:
    return str(value)


def _range(value: Any) -> OptionTargetRange:
    if isinstance(value, dict):
        minimum = value.get("min", value.get("minimum", 0))
        maximum = value.get("max", value.get("maximum", minimum))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        minimum, maximum = value[:2]
    else:
        minimum = maximum = 0
    try:
        minimum, maximum = int(minimum), int(maximum)
    except TypeError, ValueError:
        minimum = maximum = 0
    return OptionTargetRange(min=max(0, minimum), max=max(0, maximum))


def _visible(
    card: dict[str, Any],
    seats: Iterable[int],
    *,
    require_all: bool = False,
    require_face_up: bool = True,
) -> bool:
    """Return engine-ACL visibility, failing closed for malformed metadata."""
    allowed = card.get("visible_for_players")
    if not isinstance(allowed, (list, tuple, set)):
        return False
    allowed_seats: set[int] = set()
    for item in allowed:
        if isinstance(item, bool) or not isinstance(item, int) or item not in range(4):
            return False
        allowed_seats.add(item)

    if require_face_up and (
        not isinstance(card.get("is_face_up"), bool) or not card["is_face_up"]
    ):
        return False

    requested_seats = tuple(seats)
    if not requested_seats:
        return False
    if require_all:
        return all(seat in allowed_seats for seat in requested_seats)
    return any(seat in allowed_seats for seat in requested_seats)


def card_index(
    world: dict[str, Any], seats: Iterable[int]
) -> dict[str, ResolvedTarget]:
    """Index visible card descriptors for option target enrichment."""
    result: dict[str, ResolvedTarget] = {}

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if "id" in value and ("name" in value or "card_id" in value):
                key = _id_key(value.get("id"))
                if _visible(value, seats):
                    name = str(value.get("name") or value.get("card_id") or "Unknown")
                    card_type = str(value.get("card_type") or "unknown")
                    result[key] = ResolvedTarget(
                        id=key,
                        name=name,
                        card_type=card_type,
                        type=card_type,
                    )
                else:
                    result[key] = ResolvedTarget(id=key, hidden=True, resolved=True)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(world)
    return result


def resolve_target(target_id: Any, cards: dict[str, ResolvedTarget]) -> ResolvedTarget:
    key = _id_key(target_id)
    target = cards.get(key)
    if target is not None:
        return target.model_copy()
    return ResolvedTarget(
        id=key, name="UNRESOLVED", card_type="unknown", type="unknown", resolved=False
    )


def _normalise_payment(value: Any, cards: dict[str, ResolvedTarget]) -> Any:
    """Keep payment structure while replacing bare target ids with descriptors."""
    if isinstance(value, dict):
        # The engine's native form is ``{target_id: {cost, payment, rule}}``.
        # Do not leave that id as the agent-facing identity: make it an explicit
        # resolved target beside the payment details.
        if value and all(isinstance(child, dict) for child in value.values()):
            native_keys = {"cost", "payment", "rule"}
            if any(native_keys.intersection(child) for child in value.values()):
                result_list: list[dict[str, Any]] = []
                for target_id, child in value.items():
                    detail = {
                        key: _normalise_payment(item, cards)
                        for key, item in child.items()
                    }
                    detail["target"] = resolve_target(target_id, cards).model_dump()
                    result_list.append(detail)
                return result_list
        result: dict[str, Any] = {}
        for key, child in value.items():
            if isinstance(child, (dict, list, tuple)):
                result[str(key)] = _normalise_payment(child, cards)
            elif str(key).isdigit() and str(key) in cards:
                result[str(key)] = resolve_target(child, cards).model_dump()
            else:
                result[str(key)] = child
        return result
    if isinstance(value, list):
        return [_normalise_payment(child, cards) for child in value]
    if isinstance(value, tuple):
        return [_normalise_payment(child, cards) for child in value]
    return value


def build_options(
    ask: dict[str, Any],
    world: dict[str, Any],
    *,
    player_n: str,
    visible_seats: Iterable[int],
) -> GameOptions:
    cards = card_index(world, visible_seats)
    options: list[GameOption] = []
    for raw in ask.get("options") or []:
        if not isinstance(raw, dict):
            continue
        target_range = _range(raw.get("target_num_range"))
        raw_targets = list(raw.get("all_legal_targets") or [])
        # A zero maximum means no target is legal, even if the engine includes a
        # stale/non-empty target catalogue in the same option.
        targets = (
            [resolve_target(item, cards) for item in raw_targets]
            if target_range.max > 0
            else []
        )
        bound = raw.get("bind_player")
        bound_seat = None
        if bound is not None:
            try:
                bound_seat = f"player{int(bound) + 1}"
            except TypeError, ValueError:
                bound_seat = str(bound)
        options.append(
            GameOption(
                id=option_id(raw.get("id")),
                name=str(raw.get("name") or ""),
                bind_id=(
                    None if raw.get("bind_id") is None else _id_key(raw.get("bind_id"))
                ),
                bound_seat=bound_seat,
                targets=targets,
                target_num_range=target_range,
                target_payment=_normalise_payment(raw.get("target_payment"), cards),
                select_rule=raw.get("select_rule"),
                required_target_traits=raw.get("required_target_traits"),
                failure_reason=raw.get("failure_reason"),
                search=bool(raw.get("search", False)),
            )
        )
    asked = []
    for item in ask.get("asked_seats", ask.get("ask_players", [])) or []:
        try:
            asked.append(f"player{int(item) + 1}")
        except TypeError, ValueError:
            asked.append(str(item))
    return GameOptions(
        player_n=player_n,
        asked_seats=asked or [player_n],
        prompt=normalise_prompt(ask.get("prompt_text", ask.get("prompt", ""))),
        event_name=ask.get("event_name"),
        ability_type=ask.get("ability_type"),
        can_decline=bool(ask.get("show_cancel", False)),
        options=options,
    )
