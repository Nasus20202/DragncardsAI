"""Shared cache for the DragnCards bot credential.

Bootstrapping a DragnCards room used to start by re-deriving the bot's
credential every time: `POST /api/v1/session` to authenticate, then
`GET /api/v1/profile` to turn the resulting token into the numeric user id that
room creation and seating need. Measured against a local backend those two calls
cost ~240 ms and ~65 ms — together over half of a ~590 ms room creation — and
neither transfers anything worth the wait. The first is expensive because it
verifies a password hash; the second because it is a second round trip for a
value that follows from the first.

DragnCards keeps an issued token valid for 30 minutes (see
``DEFAULT_TTL_SECONDS``), so that work is repeated with no result that differs.
This module keeps the answer in Valkey rather than in this process, because the
repository forbids services holding state in memory and because a shared entry
means the saving survives a restart and is not re-paid once per replica.

The token is a credential, so it is confined to two places: the JSON value this
module writes to Valkey, and the ``authorization`` header of a DragnCards
request. It is never logged, never attached to a span, and never placed in an
exception message. The game-service's RESP client records only ``parts[0]`` as
``db.operation.name``, so command arguments never reach a span — a property this
module depends on and which must stay true.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from game_service.dragncards.http_client import get_auth_token, get_user_id

logger = logging.getLogger(__name__)

KEY_PREFIX = "game-service:dragncards-auth:"

# DragnCards issues the token through ``DragnCardsWeb.APIAuthPlug.create/3``,
# which stores it in ``Pow.Store.CredentialsCache``. In the pinned upstream
# (pow 1.0.27) that store is declared with ``ttl: :timer.minutes(30)`` and
# DragnCards' ``config :dragncards, :pow`` sets no ``:ttl`` override, so 30
# minutes is the lifetime. ``APIAuthPlug.fetch/2`` reads the store without
# rewriting the entry, so the clock runs from issue and is not extended by use.
#
# The default cached lifetime is half of that. An entry read at the last instant
# before it expires therefore still carries ~15 minutes of validity, which is
# ample for the single room bootstrap that follows it. A longer TTL would narrow
# that margin without removing another round trip — one cached credential already
# serves every room created in its window — and a shorter one would give the
# saving back for no additional safety.
DRAGNCARDS_TOKEN_LIFETIME_SECONDS = 1800.0
DEFAULT_TTL_SECONDS = 900.0


class RespCommand(Protocol):
    """The one Valkey operation this module needs.

    Declared structurally so the cache can be unit-tested against a stub without
    a Valkey instance, and so it is not coupled to which of the service's two
    equivalent RESP clients it is handed.
    """

    async def execute(self, *parts: object) -> Any: ...


@dataclass(frozen=True)
class DragnCardsIdentity:
    """A DragnCards session token and the user id it belongs to.

    ``cached`` records where this instance came from. A caller that finds the
    credential unusable needs to know whether it was reading a stored answer
    (which should be discarded) or one it just derived (which should not, because
    discarding it would loop).
    """

    token: str
    user_id: int
    cached: bool = False


def _ttl_int(seconds: float) -> int:
    """Round a TTL to whole seconds for ``SETEX``.

    A configured positive TTL never collapses to ``0``, which would silently
    disable the cache; only a non-positive value disables it. Mirrors the
    agent-orchestrator model cache, whose TTL handling this follows.
    """
    if seconds <= 0:
        return 0
    return max(1, round(seconds))


class DragnCardsAuthCache:
    """Resolves the DragnCards credential, reusing a cached one when it exists.

    With no ``valkey`` connection, or a non-positive TTL, the cache is inert and
    every call authenticates live — which is exactly the behaviour that existed
    before this module, so unit tests and in-memory runs need no Valkey.
    """

    def __init__(
        self,
        http_url: str,
        email: str,
        password: str,
        *,
        valkey: RespCommand | None = None,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self._http_url = http_url
        self._email = email
        self._password = password
        self._valkey = valkey
        self._ttl = _ttl_int(ttl_seconds)
        self._key = self._build_key(http_url, email)

    @property
    def enabled(self) -> bool:
        return self._valkey is not None and self._ttl > 0

    @property
    def key(self) -> str:
        return self._key

    @staticmethod
    def _build_key(http_url: str, email: str) -> str:
        """Derive the cache key from the backend URL and the account.

        Both are included so that repointing the service at another DragnCards
        deployment, or changing ``BOT_EMAIL``, misses rather than serving a
        credential minted somewhere else. Both are hashed because the key name is
        the part of a cache entry that surfaces in operational tooling — ``KEYS``
        output, slow logs, dashboards — and the bot's address does not need to be
        there for the lookup to work. The NUL separator keeps the two fields from
        running together into an ambiguous input.
        """
        digest = hashlib.sha256(f"{http_url}\0{email}".encode()).hexdigest()
        return f"{KEY_PREFIX}{digest[:32]}"

    async def resolve(self) -> DragnCardsIdentity:
        """Return a usable credential, from the cache when one is stored."""
        cached = await self._read()
        if cached is not None:
            return cached
        return await self.refresh()

    async def refresh(self) -> DragnCardsIdentity:
        """Derive a credential live and store it, ignoring anything cached."""
        token = await get_auth_token(self._http_url, self._email, self._password)
        user_id = await get_user_id(self._http_url, token)
        await self._write(token, user_id)
        return DragnCardsIdentity(token=token, user_id=user_id, cached=False)

    async def invalidate(self) -> None:
        """Drop the stored credential so the next resolve derives a new one.

        Best-effort: a Valkey failure here leaves the stale entry to expire on
        its own TTL, which is worse than evicting it but not worth failing a
        request over.
        """
        if self._valkey is None:
            return
        try:
            await self._valkey.execute("DEL", self._key)
        except Exception:
            logger.warning(
                "DragnCards credential cache DEL failed for key %r",
                self._key,
                exc_info=True,
            )

    async def _read(self) -> DragnCardsIdentity | None:
        """Read the stored credential, or ``None`` for anything unusable.

        A miss, an unreachable Valkey, a reset connection mid-command, and a
        value that is not the shape this module wrote are all reported the same
        way: as an absent entry. The caller then authenticates live, so the
        feature degrades to being slower rather than broken. The game-service
        opens a fresh TCP connection per command, which makes a transport error a
        live possibility rather than a theoretical one (see DRA-35).
        """
        if not self.enabled:
            return None
        assert self._valkey is not None
        try:
            raw = await self._valkey.execute("GET", self._key)
        except Exception:
            logger.warning(
                "DragnCards credential cache GET failed for key %r",
                self._key,
                exc_info=True,
            )
            return None
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            token = value["token"]
            user_id = int(value["user_id"])
        except Exception:
            # Written by an older or a different shape. Reporting it as a miss
            # re-derives and overwrites it, which self-heals; propagating would
            # turn a stale cache entry into a failed room creation.
            logger.warning(
                "DragnCards credential cache holds an unusable value at key %r; "
                "treating as a miss",
                self._key,
            )
            return None
        if not isinstance(token, str) or not token:
            logger.warning(
                "DragnCards credential cache holds no token at key %r; "
                "treating as a miss",
                self._key,
            )
            return None
        return DragnCardsIdentity(token=token, user_id=user_id, cached=True)

    async def _write(self, token: str, user_id: int) -> None:
        """Store the credential under the configured TTL, best-effort.

        The token and the user id go in as one value. The id is a pure function
        of the token, so separate entries could expire independently and leave a
        token whose id has to be re-fetched, or an id that no longer belongs to
        the token beside it.
        """
        if not self.enabled:
            return
        assert self._valkey is not None
        try:
            await self._valkey.execute(
                "SETEX",
                self._key,
                str(self._ttl),
                json.dumps({"token": token, "user_id": user_id}),
            )
        except Exception:
            logger.warning(
                "DragnCards credential cache SETEX failed for key %r",
                self._key,
                exc_info=True,
            )
