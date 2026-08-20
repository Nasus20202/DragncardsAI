"""Client-side adapter for the vendored marvel-lcg engine."""

from game_service.marvel_lcg.client import (
    MarvelLcgAuthenticationError,
    MarvelLcgContentTypeError,
    MarvelLcgError,
    MarvelLcgHttpClient,
    MarvelLcgClient,
    NewGameDescriptor,
)
from game_service.marvel_lcg.frames import (
    FrameDescriptor,
    FrameBuffer,
    MarvelLcgRenderSocket,
    MarvelLcgWebSocket,
    PromptSignature,
    StuckPromptError,
)
from game_service.marvel_lcg.platform import MarvelLcgIdentity, MarvelLcgPlatform

__all__ = [
    "FrameBuffer",
    "FrameDescriptor",
    "MarvelLcgAuthenticationError",
    "MarvelLcgContentTypeError",
    "MarvelLcgError",
    "MarvelLcgHttpClient",
    "MarvelLcgClient",
    "MarvelLcgIdentity",
    "MarvelLcgPlatform",
    "MarvelLcgRenderSocket",
    "MarvelLcgWebSocket",
    "NewGameDescriptor",
    "PromptSignature",
    "StuckPromptError",
]
