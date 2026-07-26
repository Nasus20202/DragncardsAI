from __future__ import annotations

from typing import Any

from dragncards_common.http_client import BaseAsyncClient


class OrchestratorClient(BaseAsyncClient):
    """HTTP client for the agent-orchestrator resume-from-context capability."""

    async def restore_session(
        self,
        *,
        game_id: str,
        conversation_context: list[dict[str, Any]],
        mode: str,
    ) -> dict[str, Any]:
        """Seed an orchestrator session from a captured conversation context.

        Calls ``POST {base}/sessions/restore`` with body
        ``{"game_id", "conversation_context", "mode"}`` and returns the response
        body, which carries ``session_id``.
        """
        response = await self._http().post(
            f"{self._base_url}/sessions/restore",
            json={
                "game_id": game_id,
                "conversation_context": conversation_context,
                "mode": mode,
            },
        )
        response.raise_for_status()
        return response.json()
