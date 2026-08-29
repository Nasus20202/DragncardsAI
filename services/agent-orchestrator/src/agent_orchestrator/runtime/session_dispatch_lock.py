"""Distributed serialization for prompts sharing one agent session."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from agent_orchestrator.storage.valkey import RespConnection

logger = logging.getLogger(__name__)

_LOCK_PREFIX = "agent-orchestrator:session-dispatch:"
_LOCK_LEASE_SECONDS = 2 * 60 * 60
_LOCK_RETRY_SECONDS = 0.1
_RELEASE_SCRIPT = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


class SessionDispatchLock:
    """A Valkey-backed lock keyed by agent session id.

    The optional connection is ``None`` in isolated unit tests that construct the
    prompt runtime directly. The application supplies a shared Valkey connection
    in production, where this lock must fail closed if coordination is unavailable.
    """

    def __init__(self, connection: RespConnection | None) -> None:
        self._connection = connection

    @asynccontextmanager
    async def for_session(self, session_id: str):
        if self._connection is None:
            yield
            return

        key = f"{_LOCK_PREFIX}{session_id}"
        token = uuid4().hex
        while True:
            acquired = await self._connection.execute(
                "SET",
                key,
                token,
                "NX",
                "PX",
                str(_LOCK_LEASE_SECONDS * 1000),
            )
            if acquired == "OK":
                break
            await asyncio.sleep(_LOCK_RETRY_SECONDS)

        try:
            yield
        finally:
            try:
                await self._connection.execute(
                    "EVAL",
                    _RELEASE_SCRIPT,
                    "1",
                    key,
                    token,
                )
            except Exception:
                # The lease still expires if release is unavailable. Never mask
                # the prompt result with a cleanup failure.
                logger.warning(
                    "Failed to release dispatch lock for session %s",
                    session_id,
                    exc_info=True,
                )
