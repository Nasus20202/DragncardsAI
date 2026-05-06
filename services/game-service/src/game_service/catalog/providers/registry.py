"""Card provider registry and defaults."""

from __future__ import annotations

from game_service.catalog.providers.base import CatalogProvider
from game_service.catalog.providers.marvel_champions import MarvelChampionsProvider

_REGISTERED_PROVIDERS: list[CatalogProvider] = [MarvelChampionsProvider()]

PROVIDERS: dict[str, CatalogProvider] = {
    provider.plugin_name: provider for provider in _REGISTERED_PROVIDERS
}

DEFAULT_PROVIDER_NAME = next(iter(PROVIDERS), None)
