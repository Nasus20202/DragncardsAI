"""Card catalog exception types."""

from __future__ import annotations


class CardCatalogError(ValueError):
    """Base exception for card catalog errors."""


class UnknownCardProviderError(CardCatalogError):
    """Raised when a requested card provider does not exist."""


class UnsupportedCardFilterError(CardCatalogError):
    """Raised when a filter name is not supported by a provider."""


class CardFilterValueError(CardCatalogError):
    """Raised when a filter value cannot be coerced or validated."""
