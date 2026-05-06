"""Plugin-aware card catalog service."""

from __future__ import annotations

from typing import Any

from game_service.catalog.exceptions import (
    CardFilterValueError,
    UnknownCardProviderError,
    UnsupportedCardFilterError,
)
from game_service.catalog.providers.base import (
    CatalogProvider,
    FilterSpec,
    PluginActionCatalog,
)
from game_service.catalog.providers.registry import DEFAULT_PROVIDER_NAME, PROVIDERS

ProviderMetadata = dict[str, Any]


def default_plugin_name() -> str | None:
    """Return the default card provider name."""
    return DEFAULT_PROVIDER_NAME


def _get_provider(provider_name: str | None) -> CatalogProvider:
    resolved_name = provider_name or DEFAULT_PROVIDER_NAME
    provider = PROVIDERS.get(resolved_name)
    if provider is None:
        available = ", ".join(sorted(PROVIDERS)) or "none"
        raise UnknownCardProviderError(
            f"Unknown card provider {resolved_name!r}. Available providers: {available}"
        )
    return provider


def supported_plugins() -> list[str]:
    """Return plugin identifiers with a registered card catalog provider."""
    return sorted(PROVIDERS)


def list_card_providers() -> list[ProviderMetadata]:
    """Return provider metadata and supported filters for card search."""
    providers: list[ProviderMetadata] = []
    for provider_name in supported_plugins():
        provider = PROVIDERS[provider_name]
        providers.append(
            {
                "provider": provider_name,
                "display_name": provider.display_name,
                "default": provider_name == DEFAULT_PROVIDER_NAME,
                "filters": provider.filters,
                "load_groups": provider.get_load_groups(),
            }
        )
    return providers


def get_card_provider(provider_name: str | None) -> ProviderMetadata:
    """Return one provider's metadata."""
    resolved_name = provider_name or DEFAULT_PROVIDER_NAME
    provider = _get_provider(resolved_name)
    return {
        "provider": resolved_name,
        "display_name": provider.display_name,
        "default": resolved_name == DEFAULT_PROVIDER_NAME,
        "filters": provider.filters,
        "load_groups": provider.get_load_groups(),
    }


def get_load_groups(provider_name: str | None) -> list[str]:
    """Return curated load group IDs for a provider, or [] if none are registered."""
    resolved_name = provider_name or DEFAULT_PROVIDER_NAME
    provider = PROVIDERS.get(resolved_name)
    if provider is None:
        return []
    return provider.get_load_groups()


def get_plugin_action_catalog(provider_name: str | None) -> PluginActionCatalog:
    """Return provider-defined plugin action metadata, or an empty catalog."""
    resolved_name = provider_name or DEFAULT_PROVIDER_NAME
    provider = PROVIDERS.get(resolved_name)
    if provider is None:
        return PluginActionCatalog()
    return provider.get_action_catalog()


def _coerce_boolean(name: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise CardFilterValueError(
        f"Invalid boolean value for filter {name!r}: {value!r}"
    )


def _coerce_integer(name: str, value: Any, spec: ProviderMetadata) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise CardFilterValueError(
            f"Invalid integer value for filter {name!r}: {value!r}"
        ) from exc

    minimum = spec.get("minimum")
    maximum = spec.get("maximum")
    if minimum is not None and result < minimum:
        raise CardFilterValueError(
            f"Filter {name!r} must be >= {minimum}; got {result}"
        )
    if maximum is not None and result > maximum:
        raise CardFilterValueError(
            f"Filter {name!r} must be <= {maximum}; got {result}"
        )
    return result


def normalize_search_filters(
    provider_name: str | None, raw_filters: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate and coerce provider-specific filter values."""
    provider = _get_provider(provider_name)
    raw_filters = raw_filters or {}
    filter_specs: dict[str, FilterSpec] = {
        item["name"]: item for item in provider.filters
    }
    allowed_names = sorted(filter_specs)

    normalized: dict[str, Any] = {}
    for name, value in raw_filters.items():
        spec = filter_specs.get(name)
        if spec is None:
            allowed = ", ".join(allowed_names)
            raise UnsupportedCardFilterError(
                f"Unsupported filter {name!r} for provider {provider.plugin_name!r}. Allowed filters: {allowed}"
            )
        if spec["type"] == "boolean":
            normalized[name] = _coerce_boolean(name, value)
        elif spec["type"] == "integer":
            normalized[name] = _coerce_integer(name, value, spec)
        else:
            normalized[name] = str(value)

    for spec in provider.filters:
        if spec["name"] not in normalized and "default" in spec:
            normalized[spec["name"]] = spec["default"]

    return normalized


def load_card_db(plugin_name: str | None = None):
    """Compatibility helper for the current default plugin."""
    provider = _get_provider(plugin_name)
    return provider.load_card_db()


def search_cards(
    name: str | None = None,
    type_code: str | None = None,
    classification: str | None = None,
    official_only: bool = True,
    limit: int = 50,
    plugin_name: str | None = None,
    filters: dict[str, Any] | None = None,
):
    """Search cards for the given plugin, defaulting to the first available provider."""
    resolved_name = plugin_name or DEFAULT_PROVIDER_NAME
    raw_filters = dict(filters or {})
    if name is not None:
        raw_filters["name"] = name
    if type_code is not None:
        raw_filters["type_code"] = type_code
    if classification is not None:
        raw_filters["classification"] = classification
    if "official_only" not in raw_filters:
        raw_filters["official_only"] = official_only
    if "limit" not in raw_filters:
        raw_filters["limit"] = limit

    normalized_filters = normalize_search_filters(resolved_name, raw_filters)
    provider = _get_provider(resolved_name)
    return provider.search_cards(normalized_filters)
