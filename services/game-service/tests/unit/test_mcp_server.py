"""
Unit tests for game_service.mcp.server.

The MCP server is auto-generated from the FastAPI app via
FastMCP.from_fastapi() and should expose the intended HTTP surface as tools,
excluding only endpoints that are intentionally hidden from MCP.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock
from fastmcp import Client

from game_service.api.app import create_app
from game_service.catalog.service import supported_plugins
from game_service.mcp.server import create_mcp_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_session(state=None):
    session = MagicMock()
    session.plugin_name = "marvel-champions"
    session.to_metadata.return_value = {
        "session_id": "sess-abc",
        "plugin_name": "marvel-champions",
        "plugin_id": 1,
        "room_slug": "abc123",
        "created_at": "2024-01-01T00:00:00+00:00",
        "frontend_url": None,
    }
    session.get_state = AsyncMock(return_value=state or {"game": {}})
    session.get_alerts = MagicMock(return_value=[{"level": "info", "text": "hi"}])
    session.get_gui_updates = MagicMock(
        return_value={"player1": {"player_n": "player1", "prompt": "choose"}}
    )
    return session


def _mock_manager(sessions=None):
    manager = MagicMock()
    _sessions = sessions or []
    manager.list_sessions = AsyncMock(return_value=[s.to_metadata() for s in _sessions])
    if _sessions:
        manager.create_session = AsyncMock(return_value=_sessions[0])
        manager.get_session = AsyncMock(return_value=_sessions[0])
    else:
        manager.create_session = AsyncMock(return_value=_mock_session())
        manager.get_session = AsyncMock(return_value=_mock_session())
    manager.delete_session = AsyncMock()
    return manager


def _make_mcp(manager=None):
    if manager is None:
        manager = _mock_manager()
    app = create_app(session_manager=manager)
    return create_mcp_server(session_manager=manager, fastapi_app=app)


# ---------------------------------------------------------------------------
# Tool names and schemas
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = {
    "list_actions",
    "list_card_providers",
    "create_game",
    "attach_game",
    "list_games",
    "execute_action",
    "get_session_actions",
    "delete_game",
    "get_game_state",
    "reset_game",
    "set_seat",
    "set_spectator",
    "send_alert",
    "save_replay",
    "set_player_count",
    "get_alerts",
    "get_gui_update",
}
EXPECTED_TOOL_NAMES |= {
    f"search_cards_{re.sub(r'[^a-zA-Z0-9]+', '_', provider).strip('_')}"
    for provider in supported_plugins()
}


async def test_tool_count():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert len(tools) == len(EXPECTED_TOOL_NAMES)


async def test_tool_names():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


async def test_health_excluded():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "health" not in names


async def test_all_tools_have_descriptions():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name!r} has no description"


async def test_execute_action_requires_session_id_and_action():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "execute_action")
    required = tool.inputSchema.get("required", [])
    assert "session_id" in required
    assert "action" in required


async def test_get_game_state_exposed_as_tool():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "get_game_state" in names


async def test_create_game_has_no_required_fields():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "create_game")
    assert tool.inputSchema.get("required", []) == []


async def test_set_player_count_requires_num_players():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "set_player_count")
    assert "num_players" in tool.inputSchema.get("required", [])


async def test_snapshot_endpoints_not_exposed_as_tools():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "export_game_state_snapshot" not in names
    assert "load_game_state_snapshot" not in names


# ---------------------------------------------------------------------------
# Resources: list
# ---------------------------------------------------------------------------

async def test_list_resources_empty_when_no_sessions():
    """No MCP resources should be exposed."""
    manager = _mock_manager()
    manager.list_sessions.return_value = []
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        resources = await client.list_resources()
    uris = {str(resource.uri) for resource in resources}
    assert uris == set()


async def test_list_resource_templates_empty():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    assert templates == []
