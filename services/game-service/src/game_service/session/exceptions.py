"""
Session exception hierarchy.

All exceptions raised by session operations are subclasses of SessionError,
which allows callers to catch them uniformly while also handling specific
subtypes for fine-grained error reporting.
"""

from __future__ import annotations


class SessionError(Exception):
    """Raised when a session operation fails."""


class SessionNotFoundError(SessionError):
    """Raised when a session ID is not found."""


class BadGameStateError(SessionError):
    """Raised when the DragnCards backend signals the game state is corrupted."""


class StateUnavailableError(SessionError):
    """Raised when the DragnCards backend cannot provide the game state."""
