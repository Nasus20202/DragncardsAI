"""Marvel Champions plugin metadata extraction helpers."""

from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from typing import Any

from game_service.catalog.providers.base import (
    DefaultCardAction,
    HotkeyAction,
    NamedActionList,
    PlayerCountLayout,
    PluginActionCatalog,
    TouchBarAction,
)

logger = logging.getLogger(__name__)

_DEFAULT_PLUGIN_JSON_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "..",
    "..",
    "..",
    "..",
    "external",
    "dragncards-mc-plugin",
    "json",
)
PLUGIN_JSON_DIR = os.environ.get("DRAGNCARDS_MC_PLUGIN_JSON_DIR", _DEFAULT_PLUGIN_JSON_DIR)


def _load_plugin_json(filename: str) -> dict[str, Any]:
    path = os.path.normpath(os.path.join(PLUGIN_JSON_DIR, filename))
    if not os.path.exists(path):
        logger.warning("Plugin metadata file not found at %s", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _canonicalize_group_id(group_id: str) -> str:
    return re.sub(r"^player\d+", "playerN", group_id)


@lru_cache(maxsize=1)
def load_groups() -> list[str]:
    groups_payload = _load_plugin_json("groups.json").get("groups", {})
    layouts_payload = _load_plugin_json("layouts.json").get("layouts", {})
    spawn_payload = _load_plugin_json("spawnExistingCardModal.json").get(
        "loadGroupIds", []
    )

    ordered_group_ids: list[str] = []

    def add_group_id(group_id: str | None):
        if not group_id:
            return
        canonical = _canonicalize_group_id(group_id)
        if canonical not in ordered_group_ids:
            ordered_group_ids.append(canonical)

    for group_id in groups_payload:
        add_group_id(group_id)

    for layout in layouts_payload.values():
        for region in layout.get("regions", {}).values():
            add_group_id(region.get("groupId"))

    for group_id in spawn_payload:
        add_group_id(group_id)

    return ordered_group_ids


@lru_cache(maxsize=1)
def build_action_catalog() -> PluginActionCatalog:
    action_lists_payload = _load_plugin_json("actionLists.json").get("actionLists", {})
    hotkeys_payload = _load_plugin_json("hotkeys.json").get("hotkeys", {})
    touch_bar_payload = _load_plugin_json("touchBar.json").get("touchBar", [])
    default_actions_payload = _load_plugin_json("defaultActions.json").get(
        "defaultActions", []
    )
    player_count_payload = _load_plugin_json("playerCountMenu.json").get(
        "playerCountMenu", []
    )

    named_action_lists = [
        NamedActionList(id=action_id, action_list=action_list)
        for action_id, action_list in sorted(action_lists_payload.items())
    ]
    hotkeys = [
        HotkeyAction(
            scope=scope,
            key=entry["key"],
            label=entry.get("label"),
            action_list=entry.get("actionList"),
            token_type=entry.get("tokenType"),
        )
        for scope, entries in hotkeys_payload.items()
        for entry in entries
    ]
    touch_bar = [
        TouchBarAction(
            id=entry["id"],
            row=row_index,
            order=order,
            action_type=entry["actionType"],
            label=entry.get("label"),
            action_list=entry.get("actionList"),
            token_type=entry.get("tokenType"),
            image_url=entry.get("imageUrl"),
        )
        for row_index, row in enumerate(touch_bar_payload)
        for order, entry in enumerate(row)
    ]
    default_actions = [
        DefaultCardAction(
            label=entry.get("label"),
            action_list=entry.get("actionList"),
            condition=entry.get("condition"),
            position=entry.get("position"),
        )
        for entry in default_actions_payload
    ]
    player_count_layouts = [
        PlayerCountLayout(
            label=str(entry["label"]),
            num_players=int(entry["numPlayers"]),
            layout_id=entry.get("layoutId"),
        )
        for entry in player_count_payload
    ]

    return PluginActionCatalog(
        named_action_lists=named_action_lists,
        hotkeys=hotkeys,
        touch_bar=touch_bar,
        default_actions=default_actions,
        player_count_layouts=player_count_layouts,
        load_groups=load_groups(),
    )
