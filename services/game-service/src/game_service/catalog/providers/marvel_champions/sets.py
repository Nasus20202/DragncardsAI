"""Marvel Champions prebuilt set catalog helpers."""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SETS_JSON_PATH = os.path.join(
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
    "fixtures",
    "cerebro",
    "sets.json",
)
SETS_JSON_PATH = os.environ.get(
    "DRAGNCARDS_MC_PLUGIN_SETS_JSON", _DEFAULT_SETS_JSON_PATH
)

SetSummary = dict[str, str]


def _load_sets_payload() -> list[dict[str, Any]]:
    path = os.path.normpath(SETS_JSON_PATH)
    if not os.path.exists(path):
        logger.warning("Set catalog file not found at %s", path)
        return []
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, list):
        return []
    return payload


@lru_cache(maxsize=1)
def load_sets() -> list[SetSummary]:
    sets: list[SetSummary] = []
    for record in _load_sets_payload():
        set_id = record.get("Id")
        name = record.get("Name")
        set_type = record.get("Type")
        if not set_id or not name or not set_type:
            continue
        sets.append({"id": str(set_id), "name": str(name), "type": str(set_type)})
    return sets


def search_sets(name: str | None = None, type: str | None = None) -> list[SetSummary]:
    normalized_name = (name or "").strip().lower()
    normalized_type = (type or "").strip().lower()

    results: list[SetSummary] = []
    for set_summary in load_sets():
        if normalized_name and normalized_name not in set_summary["name"].lower():
            continue
        if normalized_type and set_summary["type"].lower() != normalized_type:
            continue
        results.append(set_summary)
    return results


def clear_sets_cache() -> None:
    load_sets.cache_clear()
