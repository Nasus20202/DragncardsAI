"""Marvel Champions prebuilt deck helpers backed by set metadata."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .cards import load_card_db
from .sets import load_sets


_SET_TYPE_LABELS = {
    "Campaign Set": "Campaign",
    "Hero Set": "Hero",
    "Leader Set": "Leader",
    "Modular Set": "Modular",
    "Nemesis Set": "Nemesis",
    "Supplementary Set": "Supplementary",
    "Villain Set": "Scenario",
}


def _deck_id_for_set(set_record: dict[str, Any]) -> str:
    set_type = _SET_TYPE_LABELS.get(set_record["type"], set_record["type"])
    return f'{set_record["name"]} ({set_type})'


def _load_group_for_card(card: Any) -> str:
    type_code = getattr(card, "type_code", None) or ""
    rules = ((getattr(card, "attributes", None) or {}).get("rules") if isinstance(getattr(card, "attributes", None), dict) else None) or getattr(getattr(card, "attributes", None), "rules", None) or ""
    if type_code == "obligation":
        return "sharedEncounterDeck"
    if type_code in {"minion", "side_scheme", "treachery"}:
        return "playerNNemesisSet"
    if type_code in {"hero", "alter_ego"}:
        return "playerNPlay1"
    if "Permanent" in str(rules):
        return "playerNPlay1"
    return "playerNDeck"


def _card_to_load_item(card: Any) -> dict[str, Any] | None:
    attributes = getattr(card, "attributes", None)
    if not attributes:
        return None
    set_id = getattr(attributes, "set_id", None)
    if not set_id:
        return None
    set_number = getattr(attributes, "set_number", None)
    quantity = 1
    if isinstance(set_number, str) and set_number.isdigit():
        quantity = 1
    return {
        "databaseId": card.database_id,
        "loadGroupId": _load_group_for_card(card),
        "quantity": quantity,
    }


@lru_cache(maxsize=1)
def load_prebuilt_decks() -> dict[str, dict[str, Any]]:
    decks: dict[str, dict[str, Any]] = {}
    cards = load_card_db()
    for set_record in load_sets():
        set_id = set_record["id"]
        load_cards = [
            load_item
            for card in cards
            if getattr(getattr(card, "attributes", None), "set_id", None) == set_id
            for load_item in [_card_to_load_item(card)]
            if load_item is not None
        ]
        decks[set_id] = {
            "id": set_id,
            "deck_id": _deck_id_for_set(set_record),
            "set_id": set_record["id"],
            "label": set_record["name"],
            "type": set_record["type"],
            "cards": load_cards,
        }
    return decks


def get_prebuilt_deck_by_id(deck_id: str) -> dict[str, Any] | None:
    decks = load_prebuilt_decks()
    deck = decks.get(deck_id)
    if deck is not None:
        return deck

    for set_record in load_sets():
        if set_record["id"] == deck_id:
            return decks.get(set_record["id"])

    return None
