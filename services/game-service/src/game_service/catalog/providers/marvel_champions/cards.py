"""Marvel Champions card normalization and search helpers."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from functools import lru_cache
from typing import Any

from game_service.catalog.providers.base import (
    CatalogCardAttributes,
    CatalogCardRecord,
    FilterSpec,
)

logger = logging.getLogger(__name__)

FILTERS: list[FilterSpec] = [
    {
        "name": "name",
        "type": "string",
        "description": "Substring match on card name (case-insensitive)",
        "match": "contains_ci",
    },
    {
        "name": "type_code",
        "type": "string",
        "description": "Exact match on Marvel Champions card type code",
        "match": "exact",
    },
    {
        "name": "classification",
        "type": "string",
        "description": "Substring match on aspect/classification",
        "match": "contains_ci",
    },
    {
        "name": "official_only",
        "type": "boolean",
        "description": "If true (default), exclude custom/unofficial cards",
        "default": True,
    },
    {
        "name": "limit",
        "type": "integer",
        "description": "Maximum number of results to return",
        "default": 50,
        "minimum": 1,
        "maximum": 200,
    },
]

PROMOTED_CARD_FIELDS = frozenset(
    {"Deleted", "Printings", "Name", "Subname", "Classification", "Traits", "Official"}
)

_DEFAULT_CARDS_PATH = os.path.join(
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
    "cards.json",
)
CARDS_PATH = os.environ.get("DRAGNCARDS_CARDS_PATH", _DEFAULT_CARDS_PATH)


def _compute_database_id(artificial_id: str) -> str:
    """Compute the DragnCards databaseId UUID from a card's ArtificialId."""
    aid = artificial_id.upper()
    if aid.isdigit():
        code = aid
    elif aid[-1] in "ABCD":
        code = aid[:-1]
    else:
        code = aid
    return str(uuid.uuid5(uuid.NAMESPACE_OID, code))


def _card_type_code(card: dict[str, Any]) -> str | None:
    type_name = (card.get("Type") or "").strip()
    if not type_name:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", type_name.lower()).strip("_")
    return normalized or None


def _snake_case(name: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value)
    return value.strip("_").lower()


def _normalize_card_attributes(
    card: dict[str, Any], printing: dict[str, Any]
) -> CatalogCardAttributes:
    attributes: dict[str, Any] = {}
    for key, value in card.items():
        if key in PROMOTED_CARD_FIELDS:
            continue
        attributes[_snake_case(key)] = value

    for key, value in printing.items():
        attributes[_snake_case(key)] = value

    attributes.setdefault("type_code", _card_type_code(card))
    return CatalogCardAttributes.model_validate(attributes)


@lru_cache(maxsize=1)
def load_card_db() -> list[CatalogCardRecord]:
    """Load and index the Marvel Champions card database."""
    path = os.path.normpath(CARDS_PATH)
    if not os.path.exists(path):
        logger.warning("Card database not found at %s — card search unavailable", path)
        return []

    with open(path, encoding="utf-8") as f:
        raw: list[dict[str, Any]] = json.load(f)

    records: list[CatalogCardRecord] = []
    skipped = 0
    for card in raw:
        if card.get("Deleted"):
            continue

        name = card.get("Name") or ""
        subname = card.get("Subname")
        official = bool(card.get("Official"))
        type_code = _card_type_code(card)
        classification = card.get("Classification")
        traits = list(card.get("Traits") or [])

        for printing in card.get("Printings", []):
            aid = printing.get("ArtificialId", "")
            if not aid:
                skipped += 1
                continue
            try:
                db_id = _compute_database_id(aid)
            except Exception:
                skipped += 1
                continue

            records.append(
                CatalogCardRecord(
                    database_id=db_id,
                    name=name,
                    subname=subname,
                    type_code=type_code,
                    classification=classification,
                    traits=traits,
                    official=official,
                    attributes=_normalize_card_attributes(card, printing),
                )
            )

    logger.info(
        "Loaded %d card records from %s (%d skipped)", len(records), path, skipped
    )
    return records


def search_cards(filters: dict[str, Any]) -> list[CatalogCardRecord]:
    """Search the Marvel Champions card database."""
    db = load_card_db()
    seen_ids: set[str] = set()
    results: list[CatalogCardRecord] = []

    name = filters.get("name")
    type_code = filters.get("type_code")
    classification = filters.get("classification")
    official_only = filters.get("official_only", True)
    limit = filters.get("limit", 50)

    name_lower = name.lower() if name else None
    classification_lower = classification.lower() if classification else None

    for card in db:
        if official_only and not card.official:
            continue
        if name_lower and name_lower not in card.name.lower():
            continue
        if type_code and card.type_code != type_code:
            continue
        if classification_lower:
            card_class = (card.classification or "").lower()
            if classification_lower not in card_class:
                continue

        if card.database_id in seen_ids:
            continue
        seen_ids.add(card.database_id)
        results.append(card)
        if len(results) >= min(limit, 200):
            break

    return results
