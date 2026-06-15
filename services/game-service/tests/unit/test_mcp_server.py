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
    "load_prebuilt_deck",
    "search_prebuilt_sets_marvel_champions",
    "create_game",
    "attach_game",
    "list_games",
    "get_session_actions",
    "delete_game",
    "get_game_state",
    # Explicit per-action helpers added by game_action_helpers router
    "next_step",
    "prev_step",
    "draw_card",
    "move_card",
    "set_card_property",
    "set_player_count_action",
    "load_cards",
    "unload_cards",
    # Marvel Champions action helpers
    "exhaust_card",
    "ready_card",
    "flip_card",
    "deal_encounter",
    "draw_boost",
    "shuffle_into_deck",
    "zero_tokens",
    "mulligan_draw_hand",
    "shadows_of_the_past",
    "player_end_phase",
    "villain_encounter_phase",
    "villain_end_phase",
    "multiple_double_sided_villains",
    "discard_minion",
    "discard_side_scheme",
    "modify_tokens",
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
    # Typed per-action helpers expose set_card_property, etc. with specific schemas
    tool = next(t for t in tools if t.name == "set_card_property")
    required = tool.inputSchema.get("required", [])
    assert "session_id" in required
    assert "instance_id" in required
    assert "property_path" in required


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


async def test_room_control_tools_not_exposed():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "reset_game" not in names
    assert "set_seat" not in names
    assert "set_spectator" not in names
    assert "send_alert" not in names
    assert "save_replay" not in names
    # Note: typed per-action helpers expose a 'set_player_count' tool; ensure
    # room-level player-count control (the HTTP-only endpoint) is excluded by
    # using a distinct operation_id on the room router. Do not assert absence
    # of the typed helper here.
    assert "get_alerts" not in names
    assert "get_gui_update" not in names


async def test_snapshot_endpoints_not_exposed_as_tools():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "export_game_state_snapshot" not in names
    assert "load_game_state_snapshot" not in names


async def test_debug_endpoints_not_exposed_as_tools():
    """Debug-only endpoints should be excluded from MCP tool discovery."""
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "get_raw_game_state_games" not in names
    assert "execute_action" not in names
    assert "raw_action" not in names


async def test_prebuilt_set_tools_are_exposed():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "search_prebuilt_sets_marvel_champions" in names


async def test_load_prebuilt_deck_tool_is_exposed():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "load_prebuilt_deck" in names


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
