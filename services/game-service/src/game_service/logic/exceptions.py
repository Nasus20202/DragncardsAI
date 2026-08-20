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
    """Raised when a session identifier matches no managed session."""


class AmbiguousSessionIdentifierError(SessionError):
    """Raised when a room slug maps to more than one managed session.

    DragnCards room slugs are unique per room, but ``attach_game`` can create
    several sessions pointing at the same room, so a slug is not guaranteed to
    identify exactly one session. When it does not, the caller must use the
    canonical UUID ``session_id`` instead of guessing.
    """


class BadGameStateError(SessionError):
    """Raised when the DragnCards backend signals the game state is corrupted."""


class StateUnavailableError(SessionError):
    """Raised when the DragnCards backend cannot provide the game state."""


class SnapshotValidationError(SessionError):
    """Raised when a snapshot document is invalid for the target session."""


class SessionLockedError(SessionError):
    """Raised when a session operation lock cannot be acquired in time."""


class EnumeratedOptionError(SessionError):
    """Raised when a platform option cannot be listed or submitted."""


class PlatformTransportError(SessionError):
    """Raised when a platform's live transport cannot complete an operation."""


class PlatformTimeoutError(PlatformTransportError):
    """Raised when a platform operation exceeds its caller-provided timeout."""
