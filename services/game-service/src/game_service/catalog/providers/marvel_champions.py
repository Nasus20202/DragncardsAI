"""
Marvel Champions card catalog provider.

Reads Cerebro card data from the plugin fixtures and computes the databaseId
UUID (uuid5/NAMESPACE_OID) used by DragnCards LOAD_CARDS, matching the Rust
implementation in the DragnCards card database builder.
"""

from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

FILTERS = [
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

LOAD_GROUPS = [
    "playerNDeck",
    "playerNDeck2",
    "playerNDiscard",
    "playerNHand",
    "playerNPlay1",
    "playerNPlay2",
    "playerNPlay3",
    "playerNPlay4",
    "playerNEngaged",
    "playerNNemesisSet",
    "sharedEncounterDeck",
    "sharedEncounterDiscard",
    "sharedEncounter2Deck",
    "sharedEncounter2Discard",
    "sharedEncounter3Deck",
    "sharedMainScheme",
    "sharedMainSchemeDeck",
    "sharedVillain",
    "sharedVillainDeck",
    "sharedVictoryDisplay",
    "sharedCampaignDeck",
]

_DEFAULT_CARDS_PATH = os.path.join(
    os.path.dirname(__file__),
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


def _card_type_code(card: dict) -> str | None:
    mapping = {
        "Hero": "hero",
        "Alter-Ego": "alter_ego",
        "Ally": "ally",
        "Event": "event",
        "Upgrade": "upgrade",
        "Support": "support",
        "Resource": "resource",
        "Villain": "villain",
        "Main Scheme": "main_scheme",
        "Side Scheme": "side_scheme",
        "Minion": "minion",
        "Attachment": "attachment",
        "Treachery": "treachery",
        "Environment": "environment",
        "Obligation": "obligation",
        "Player Side Scheme": "player_side_scheme",
        "Leader": "leader",
    }
    return mapping.get(card.get("Type", ""))


@lru_cache(maxsize=1)
def load_card_db() -> list[dict[str, Any]]:
    """Load and index the Marvel Champions card database."""
    import json

    path = os.path.normpath(CARDS_PATH)
    if not os.path.exists(path):
        logger.warning("Card database not found at %s — card search unavailable", path)
        return []

    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    records: list[dict[str, Any]] = []
    skipped = 0
    for card in raw:
        if card.get("Deleted"):
            continue
        name = card.get("Name") or ""
        subname = card.get("Subname")
        official = bool(card.get("Official"))
        type_code = _card_type_code(card)
        classification = card.get("Classification")
        traits = card.get("Traits") or []

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
                {
                    "database_id": db_id,
                    "name": name,
                    "subname": subname,
                    "type_code": type_code,
                    "classification": classification,
                    "traits": traits,
                    "official": official,
                    "pack_id": printing.get("PackId"),
                    "set_id": printing.get("SetId"),
                    "pack_number": printing.get("PackNumber"),
                }
            )

    logger.info(
        "Loaded %d card records from %s (%d skipped)", len(records), path, skipped
    )
    return records


def search_cards(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Search the Marvel Champions card database."""
    db = load_card_db()
    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

    name = filters.get("name")
    type_code = filters.get("type_code")
    classification = filters.get("classification")
    official_only = filters.get("official_only", True)
    limit = filters.get("limit", 50)

    name_lower = name.lower() if name else None
    classification_lower = classification.lower() if classification else None

    for card in db:
        if official_only and not card["official"]:
            continue
        if name_lower and name_lower not in card["name"].lower():
            continue
        if type_code and card["type_code"] != type_code:
            continue
        if classification_lower:
            card_class = (card["classification"] or "").lower()
            if classification_lower not in card_class:
                continue
        db_id = card["database_id"]
        if db_id in seen_ids:
            continue
        seen_ids.add(db_id)
        results.append(card)
        if len(results) >= min(limit, 200):
            break

    return results
