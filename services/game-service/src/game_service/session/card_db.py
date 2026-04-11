"""
Card database loader for the Marvel Champions plugin.

Reads Cerebro card data from the plugin fixtures and computes the databaseId
UUID (uuid5/NAMESPACE_OID) used by DragnCards LOAD_CARDS, matching the Rust
implementation in the DragnCards card database builder.

The card data is loaded once at module import and cached in memory.

DatabaseId computation rules (from dragncards/src/dragncards/database.rs):
  - Purely numeric ArtificialId (e.g. "23012") → use as-is
  - ArtificialId ending in A/B/C/D (e.g. "01040A") → strip trailing letter
  - Otherwise → use as-is (handles special/unofficial IDs)
  → databaseId = str(uuid.uuid5(uuid.NAMESPACE_OID, code))

Only official cards (Official == True, Deleted == False) are indexed.
"""

from __future__ import annotations

import logging
import os
import uuid
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

# Path to the Cerebro cards fixture — relative to this file's location.
# Adjust via DRAGNCARDS_CARDS_PATH env var if running outside the repo.
_DEFAULT_CARDS_PATH = os.path.join(
    os.path.dirname(__file__),
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
    """
    Compute the DragnCards databaseId UUID from a card's ArtificialId.

    Mirrors the Rust uuid() function in dragncards/src/dragncards/database.rs.
    """
    aid = artificial_id.upper()
    if aid.isdigit():
        code = aid
    elif aid[-1] in "ABCD":
        code = aid[:-1]
    else:
        # Custom/unofficial IDs (e.g. "583884764084305920/01067") — use as-is.
        # These are not typically searched by name so we still index them.
        code = aid
    return str(uuid.uuid5(uuid.NAMESPACE_OID, code))


def _card_type_code(card: dict) -> str | None:
    """
    Map Cerebro card Type string to a marvelcdb-style type_code.
    Returns lowercase snake_case or None if unrecognised.
    """
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
    """
    Load and index the Cerebro card database.

    Returns a flat list of card records, one per printing of each official card.
    Each record contains:
      - database_id: str (UUID used by LOAD_CARDS)
      - name: str
      - subname: str | None
      - type_code: str | None  (e.g. "hero", "ally", "villain")
      - classification: str | None  (e.g. "Justice", "Aggression")
      - traits: list[str]
      - official: bool
      - pack_id: str | None  (UUID of the pack)
      - set_id: str | None   (UUID of the set)
      - pack_number: str | None  (position within pack, e.g. "40A")

    Cached after first call — safe to call repeatedly.
    """
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


def search_cards(
    name: str | None = None,
    type_code: str | None = None,
    classification: str | None = None,
    official_only: bool = True,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Search the card database.

    Args:
        name: Substring match on card name (case-insensitive).
        type_code: Exact match on type_code (e.g. "hero", "ally", "villain").
        classification: Substring match on classification/aspect
                        (e.g. "Justice", "Aggression", "Basic").
        official_only: If True (default), exclude custom/unofficial cards.
        limit: Maximum number of results to return (default 50, max 200).

    Returns:
        List of matching card records (each has database_id, name, type_code, etc.)
        De-duplicated by database_id — only the first printing of each card is returned.
    """
    db = load_card_db()
    seen_ids: set[str] = set()
    results: list[dict[str, Any]] = []

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
