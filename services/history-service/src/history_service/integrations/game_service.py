from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from dragncards_common.http_client import BaseAsyncClient


@dataclass(frozen=True)
class BranchSession:
    """A freshly created game-service session and the room it owns.

    ``room_slug`` comes back on the same ``POST /games`` response that assigns
    the session id, so a caller that needs to name or link the new room never
    has to list every live session to find it again.
    """

    session_id: str
    room_slug: str | None


# The replay endpoint suffix is taken from a stored event payload, so it is
# treated as untrusted input. Recorded game-service actions resolve to either
# the generic ``actions`` endpoint or ``actions/<action_name>`` (and legacy
# payloads stored a bare ``<action_name>``). Anything else -- extra path
# segments, traversal, query/encoded characters -- is rejected before it can be
# forwarded against the trusted internal game-service.
_ACTION_NAME = r"[A-Za-z0-9_-]{1,64}"
_REPLAY_ACTION_PATH = re.compile(rf"^(?:actions(?:/{_ACTION_NAME})?|{_ACTION_NAME})$")


class GameServiceClient(BaseAsyncClient):
    """HTTP client for the game-service snapshot + action-replay endpoints."""

    def _games_url(self, *segments: str) -> httpx.URL:
        """Build a ``/games/...`` URL with each segment percent-encoded.

        Segments flow into a trusted internal API; encoding them (rather than
        f-string interpolation) ensures a crafted id can never inject extra path
        segments or traversal into the request line.
        """
        encoded = "/".join(quote(segment, safe="") for segment in ["games", *segments])
        return httpx.URL(f"{self._base_url}/{encoded}")

    async def create_session(
        self, plugin_name: str, *, ephemeral: bool = False
    ) -> BranchSession:
        """Create a fresh game-service session and return it with its room.

        Used by ``mode="new"`` restore: a branchable restore needs a real
        DragnCards room (snapshot import + forward replay target). The session
        id returned by ``POST /games`` is the new ``game_id`` for the branch.

        The same response carries the new room's ``room_slug``, so it is
        returned alongside the id rather than discarded — a caller that has to
        name or link the room otherwise has to list every live session and
        search it by id, which is both a wasted round trip and a race (the
        session can be reaped between the two calls).

        When ``ephemeral`` is true the game-service tags the session as a
        non-emitting, server-reaped reconstruction (used only for viewing).
        """
        response = await self._http().post(
            f"{self._base_url}/games",
            json={"plugin_name": plugin_name, "ephemeral": ephemeral},
        )
        response.raise_for_status()
        body = response.json()
        session_id: Any = None
        room_slug: Any = None
        if isinstance(body, dict):
            session = body.get("session")
            if isinstance(session, dict):
                session_id = session.get("session_id")
                room_slug = session.get("room_slug")
            if session_id is None:
                session_id = body.get("session_id")
            if room_slug is None:
                room_slug = body.get("room_slug")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError(
                "game-service create_session response missing 'session_id'"
            )
        return BranchSession(
            session_id=session_id,
            room_slug=room_slug if isinstance(room_slug, str) and room_slug else None,
        )

    async def delete_session(self, game_id: str) -> None:
        """Delete a game-service session (best-effort cleanup of a branch room).

        Used to roll back a ``mode="new"`` restore that created a real room but
        then failed before completing, so a half-built branch is not left
        behind. Raises on transport/HTTP error; callers wrap this best-effort.
        """
        response = await self._http().delete(self._games_url(game_id))
        response.raise_for_status()

    async def get_snapshot(self, game_id: str) -> dict[str, Any]:
        """Export a full ``GameStateSnapshot`` document for ``game_id``."""
        response = await self._http().get(self._games_url(game_id, "snapshot"))
        response.raise_for_status()
        return response.json()

    async def load_snapshot(
        self, game_id: str, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        """Import a snapshot document into a game-service session (set_game)."""
        response = await self._http().put(
            self._games_url(game_id, "snapshot"),
            json=snapshot,
        )
        response.raise_for_status()
        return response.json()

    async def get_state(self, game_id: str) -> dict[str, Any]:
        response = await self._http().get(self._games_url(game_id, "state"))
        response.raise_for_status()
        return response.json()

    async def replay_action(
        self, game_id: str, action: dict[str, Any]
    ) -> dict[str, Any]:
        """Re-execute a single recorded game-mutating action against a session.

        The stored ``game-service`` event payload describes the action via
        ``action_path`` (the game-service endpoint suffix, e.g. ``actions`` or
        ``actions/move_card``) and ``action_args`` (the JSON body). This
        re-invokes that endpoint forward.

        ``action_path`` originates from stored data and is therefore validated
        against the known replay-endpoint shape before use; an arbitrary path is
        rejected rather than forwarded.
        """
        path = action.get("action_path")
        if not path:
            raise ValueError(
                "game-service event payload missing 'action_path' for replay"
            )
        suffix = path.lstrip("/")
        if not _REPLAY_ACTION_PATH.fullmatch(suffix):
            raise ValueError(
                f"game-service replay rejected disallowed action_path: {path!r}"
            )
        args = action.get("action_args", {})
        # Each suffix segment is encoded individually so a validated multi-segment
        # path (e.g. ``actions/move_card``) keeps its structure without allowing
        # any other character to break out of a single segment.
        response = await self._http().post(
            self._games_url(game_id, *suffix.split("/")),
            json=args,
        )
        response.raise_for_status()
        return response.json()
