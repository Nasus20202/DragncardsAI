"""Marvel Champions provider implementation."""

from __future__ import annotations

from typing import Any

from game_service.catalog.providers.base import (
    CatalogCardRecord,
    CatalogProvider,
    FilterSpec,
    PluginActionCatalog,
)

from .cards import FILTERS, load_card_db, search_cards
from .plugin_metadata import build_action_catalog, load_groups


class MarvelChampionsProvider(CatalogProvider):
    @property
    def plugin_name(self) -> str:
        return "marvel-champions"

    @property
    def display_name(self) -> str:
        return "Marvel Champions"

    @property
    def filters(self) -> list[FilterSpec]:
        return FILTERS

    def load_card_db(self) -> list[CatalogCardRecord]:
        return load_card_db()

    def search_cards(self, filters: dict[str, Any]) -> list[CatalogCardRecord]:
        return search_cards(filters)

    def get_load_groups(self) -> list[str]:
        return load_groups()

    def get_action_catalog(self) -> PluginActionCatalog:
        return build_action_catalog()
