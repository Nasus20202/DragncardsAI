"""Enum-like type definitions for Marvel Champions–scoped fields.

These use typing.Literal so Pydantic/OpenAPI will include the allowed
values in generated schemas. Values are derived from the Marvel Champions
plugin JSON metadata under external/dragncards-mc-plugin/json/.
"""

from __future__ import annotations

from typing import Literal

from game_service.catalog.providers.marvel_champions import plugin_metadata

# Canonical group IDs (playerN used instead of player1..player4 where applicable)
_CANONICAL_GROUP_IDS = plugin_metadata.load_groups()


# Expand canonical 'playerN' placeholders into concrete player1..player4 values
def _expand_player_n(ids: list[str]) -> list[str]:
    out: list[str] = []
    for gid in ids:
        if "playerN" in gid:
            for i in range(1, 5):
                out.append(gid.replace("playerN", f"player{i}"))
        else:
            out.append(gid)
    return out


_GROUP_IDS = _expand_player_n(_CANONICAL_GROUP_IDS)
GroupId = Literal[tuple(_GROUP_IDS)]


# Player identifiers used throughout typed actions
PlayerN = Literal["player1", "player2", "player3", "player4", "shared"]


# Layout IDs from the plugin's player count menu (may be empty if plugin lacks layouts)
_CAT = plugin_metadata.build_action_catalog()
_LAYOUT_IDS = [p.layout_id for p in _CAT.player_count_layouts if p.layout_id]
LayoutId = Literal[tuple(_LAYOUT_IDS)] if _LAYOUT_IDS else Literal[""]
