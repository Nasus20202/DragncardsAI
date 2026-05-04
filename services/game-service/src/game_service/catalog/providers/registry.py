"""Card provider registry and defaults."""

from __future__ import annotations

from typing import Any

from game_service.catalog.providers import marvel_champions

PROVIDERS: dict[str, dict[str, Any]] = {
    "marvel-champions": {
        "display_name": "Marvel Champions",
        "filters": marvel_champions.FILTERS,
        "load_groups": marvel_champions.LOAD_GROUPS,
        "load_db": marvel_champions.load_card_db,
        "search": marvel_champions.search_cards,
    }
}

DEFAULT_PROVIDER_NAME = next(iter(PROVIDERS), None)
