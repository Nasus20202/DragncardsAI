"""
End-to-end tests: HTTP API + MCP tools + concurrent access.

Requires a running DragnCards instance with the Marvel Champions plugin.

Run with:
    pytest tests/integration/test_e2e.py -v

Note: All tests that call endpoints involving WebSocket operations use
httpx.AsyncClient with ASGI transport so the event loop stays free for
background WebSocket receiver tasks.
"""

import asyncio
import json
import os

import httpx
import pytest

from game_service.api.app import create_app
from game_service.mcp.server import _dispatch_tool
from game_service.session.manager import SessionManager

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")

PLUGIN_REGISTRY = {
    "marvel-champions": {
        "id": int(os.environ.get("MC_PLUGIN_ID", "1")),
        "version": int(os.environ.get("MC_PLUGIN_VERSION", "3")),
        "name": "Marvel Champions",
    }
}


@pytest.fixture
def manager():
    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=DEV_USER_EMAIL,
        password=DEV_USER_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
    )


@pytest.fixture
def app(manager):
    return create_app(session_manager=manager)


# ---------------------------------------------------------------------------
# 7.1  End-to-end via HTTP API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_http_game_lifecycle(app, manager):
    """
    Full lifecycle via HTTP:
      1. Create a game session
      2. Query initial state (has 'game' key)
      3. Execute next_step action (state updates)
      4. Delete session
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Create
        create_resp = await client.post(
            "/games", json={"plugin_name": "marvel-champions"}
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["session_id"]

        try:
            # 2. Query initial state
            state_resp = await client.get(f"/games/{session_id}/state")
            assert state_resp.status_code == 200
            state_before = state_resp.json()["state"]
            assert state_before is not None
            assert "game" in state_before

            # 3. Execute next_step
            action_resp = await client.post(
                f"/games/{session_id}/actions",
                json={"type": "next_step"},
            )
            assert action_resp.status_code == 200
            state_after = action_resp.json()["state"]
            assert state_after is not None
            assert "game" in state_after

        finally:
            # 4. Delete
            del_resp = await client.delete(f"/games/{session_id}")
            assert del_resp.status_code == 200

        # Session should be gone
        gone = await client.get(f"/games/{session_id}/state")
        assert gone.status_code == 404


# ---------------------------------------------------------------------------
# 7.2  End-to-end via MCP tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_mcp_game_lifecycle(manager):
    """
    Full lifecycle via MCP tool dispatch:
      1. create_game
      2. get_game_state
      3. execute_action (next_step)
      4. delete_game
    """
    # 1. Create
    results = await _dispatch_tool(
        "create_game", {"plugin_name": "marvel-champions"}, manager
    )
    assert results
    text = results[0].text
    assert "session_id" in text
    # Parse session_id from the JSON embedded in the response
    meta = json.loads(text.split("\n", 1)[1])  # skip "Game session created:\n"
    session_id = meta["session_id"]

    try:
        # 2. Get state
        state_results = await _dispatch_tool(
            "get_game_state", {"session_id": session_id}, manager
        )
        state_text = state_results[0].text
        assert session_id in state_text
        assert "game" in state_text.lower()

        # 3. Execute next_step
        action_results = await _dispatch_tool(
            "execute_action",
            {"session_id": session_id, "action": {"type": "next_step"}},
            manager,
        )
        assert action_results
        assert "Action executed" in action_results[0].text

        # 4. List games — session should appear
        list_results = await _dispatch_tool("list_games", {}, manager)
        assert session_id in list_results[0].text

    finally:
        # 5. Delete
        del_results = await _dispatch_tool(
            "delete_game", {"session_id": session_id}, manager
        )
        assert "deleted" in del_results[0].text.lower()

    # Session should be gone — _dispatch_tool returns error text (doesn't raise)
    gone_results = await _dispatch_tool(
        "get_game_state", {"session_id": session_id}, manager
    )
    assert "not found" in gone_results[0].text.lower()


# ---------------------------------------------------------------------------
# 7.3  Concurrent HTTP + MCP access to the same session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_concurrent_http_and_mcp(app, manager):
    """
    Both HTTP and MCP interfaces can concurrently read the same session state
    and both return consistent results.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session via HTTP
        create_resp = await client.post(
            "/games", json={"plugin_name": "marvel-champions"}
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["session_id"]

        try:
            # Concurrently query state via HTTP and MCP
            async def http_query():
                resp = await client.get(f"/games/{session_id}/state")
                return resp.json()["state"]

            async def mcp_query():
                results = await _dispatch_tool(
                    "get_game_state", {"session_id": session_id}, manager
                )
                return results[0].text

            http_state, mcp_text = await asyncio.gather(http_query(), mcp_query())

            # Both should return valid state
            assert http_state is not None
            assert "game" in http_state
            assert session_id in mcp_text

            # Execute an action via HTTP, then verify MCP sees updated state
            action_resp = await client.post(
                f"/games/{session_id}/actions",
                json={"type": "next_step"},
            )
            assert action_resp.status_code == 200

            # MCP should see updated state
            mcp_after = await _dispatch_tool(
                "get_game_state", {"session_id": session_id}, manager
            )
            assert "game" in mcp_after[0].text.lower()

        finally:
            await manager.delete_session(session_id)
