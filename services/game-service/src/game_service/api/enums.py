"""Enum-like types for platform-scoped game fields.

The old module loaded the DragnCards plugin JSON while importing the application,
and the first lazy version still loaded it while generating OpenAPI.  These are
the stable DragnCards action vocabularies captured in source instead: schema
generation and request validation never depend on a plugin filesystem checkout.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BeforeValidator

from game_service.logic.platform import DRAGNCARDS_PLATFORM


def _expand_player_n(ids: list[str]) -> list[str]:
    out: list[str] = []
    for gid in ids:
        if "playerN" in gid:
            for i in range(1, 5):
                out.append(gid.replace("playerN", f"player{i}"))
        else:
            out.append(gid)
    return out


_DRAGNCARDS_GROUP_IDS = tuple(
    _expand_player_n(
        [
            "sharedEncounterDeck",
            "sharedEncounterDiscard",
            "sharedMainSchemeDeck",
            "sharedMainSchemeDiscard",
            "sharedEncounter2Deck",
            "sharedEncounter2Discard",
            "sharedEncounter3Deck",
            "sharedInfinityGauntletDeck",
            "sharedInfinityGauntletDiscard",
            "sharedCampaignDeck",
            "sharedVictoryDisplay",
            "sharedVillain",
            "sharedVillainDeck",
            "sharedVillainDiscard",
            "sharedMainScheme",
            "sharedOutOfPlay",
            "playerNHand",
            "playerNDeck",
            "playerNDiscard",
            "playerNDeck2",
            "playerNDiscard2",
            "playerNPlay1",
            "playerNPlay2",
            "playerNPlay3",
            "playerNPlay4",
            "playerNEngaged",
            "playerNEvent",
            "playerNNemesisSet",
            "playerNOutOfPlay",
        ]
    )
)
_DRAGNCARDS_LAYOUT_IDS = (
    "standard1Player",
    "standard2Player",
    "standard3Player",
    "standard4Player",
)


def enum_values(
    kind: Literal["group", "layout"], platform: str = DRAGNCARDS_PLATFORM
) -> list[str]:
    """Return a platform vocabulary without touching plugin metadata files."""
    if platform != DRAGNCARDS_PLATFORM:
        return []
    return list(_DRAGNCARDS_GROUP_IDS if kind == "group" else _DRAGNCARDS_LAYOUT_IDS)


def _validate_enum(value: Any, kind: Literal["group", "layout"]) -> str:
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    allowed = enum_values(kind)
    if value not in allowed:
        raise ValueError(f"Unknown {kind} id: {value!r}")
    return value


class _LazyEnumSchema:
    def __init__(self, kind: Literal["group", "layout"]) -> None:
        self.kind = kind

    def __get_pydantic_json_schema__(
        self, core_schema: Any, handler: Any
    ) -> dict[str, Any]:
        schema = handler(core_schema)
        allowed = enum_values(self.kind)
        schema["enum"] = allowed
        return schema


GroupId = Annotated[
    str,
    BeforeValidator(lambda value: _validate_enum(value, "group")),
    _LazyEnumSchema("group"),
]

PlayerN = Literal["player1", "player2", "player3", "player4", "shared"]

# A DragnCards seat is narrower than PlayerN: ``shared`` can target a group but
# can never be sat in.
SeatId = Literal["player1", "player2", "player3", "player4"]

LayoutId = Annotated[
    str,
    BeforeValidator(lambda value: _validate_enum(value, "layout")),
    _LazyEnumSchema("layout"),
]
