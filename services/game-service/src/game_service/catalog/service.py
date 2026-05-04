"""Plugin-aware card catalog service."""

from __future__ import annotations

from typing import Any, Callable

from game_service.catalog.providers import marvel_champions

CardSearchFn = Callable[..., list[dict[str, Any]]]

_SEARCH_PROVIDERS: dict[str, CardSearchFn] = {
    "marvel-champions": marvel_champions.search_cards,
}


def load_card_db(plugin_name: str = "marvel-champions") -> list[dict[str, Any]]:
    """Compatibility helper for the current default plugin."""
    if plugin_name == "marvel-champions":
        return marvel_champions.load_card_db()
    return []


def search_cards(
    name: str | None = None,
    type_code: str | None = None,
    classification: str | None = None,
    official_only: bool = True,
    limit: int = 50,
    plugin_name: str = "marvel-champions",
) -> list[dict[str, Any]]:
    """Search cards for the given plugin, defaulting to Marvel Champions."""
    provider = _SEARCH_PROVIDERS.get(plugin_name)
    if provider is None:
        return []
    return provider(
        name=name,
        type_code=type_code,
        classification=classification,
        official_only=official_only,
        limit=limit,
    )
