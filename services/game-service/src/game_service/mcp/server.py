"""
MCP server for the Game Service.

Exposes five MCP tools and one MCP resource, all backed by the shared
SessionManager instance:

Tools:
  create_game       — create a new game session
  list_games        — list active sessions
  get_game_state    — return current state formatted for LLM consumption
  execute_action    — execute a game action, return new state
  delete_game       — end a session

Resource:
  game://{session_id}/state  — current game state as an MCP resource

The MCP server is designed to run in the same process as the FastAPI app,
sharing the same SessionManager. It is exposed via stdio transport so that
MCP clients (like Claude Desktop) can launch the service and communicate
over stdin/stdout.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.lowlevel.server import ReadResourceContents
from mcp.types import (
    CallToolResult,
    EmbeddedResource,
    ReadResourceResult,
    Resource,
    TextContent,
    TextResourceContents,
    Tool,
)

from game_service.session.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    RawAction,
    SetCardPropertyAction,
)
from game_service.session.manager import (
    SessionError,
    SessionManager,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: format state for LLM consumption
# ---------------------------------------------------------------------------


def _format_state_for_llm(session_id: str, state: Any) -> str:
    """
    Convert raw DragnCards game state into structured text suitable for LLMs.

    The state is a nested JSON object. We serialize it as pretty-printed JSON
    with a short preamble — models can parse structured JSON easily.
    """
    if state is None:
        return f"Session {session_id}: no game state available yet."
    state_json = json.dumps(state, indent=2)
    return f"Game session: {session_id}\n\nState:\n{state_json}"


def _action_from_dict(data: dict) -> Any:
    """Deserialize an action dict into a typed GameAction using the 'type' discriminator."""
    action_type = data.get("type")
    constructors = {
        "move_card": MoveCardAction,
        "draw_card": DrawCardAction,
        "next_step": NextStepAction,
        "prev_step": PrevStepAction,
        "set_card_property": SetCardPropertyAction,
        "raw": RawAction,
    }
    cls = constructors.get(action_type)
    if cls is None:
        raise ValueError(
            f"Unknown action type {action_type!r}. "
            f"Valid types: {list(constructors.keys())}"
        )
    return cls(**{k: v for k, v in data.items() if k != "type"})


# ---------------------------------------------------------------------------
# MCP server factory
# ---------------------------------------------------------------------------


def create_mcp_server(session_manager: SessionManager) -> Server:
    """
    Build and return an MCP Server wired to the given SessionManager.

    The returned server should be run via one of the MCP transport helpers
    (e.g. stdio_server) in the process entrypoint.
    """
    server = Server("game-service")

    # ------------------------------------------------------------------
    # Tool definitions (with JSON Schema parameter descriptions)
    # ------------------------------------------------------------------

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="create_game",
                description=(
                    "Create a new DragnCards game session. "
                    "Returns the session ID and metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "plugin_name": {
                            "type": "string",
                            "description": "Plugin identifier for the game (e.g. 'marvel-champions')",
                            "default": "marvel-champions",
                        }
                    },
                    "required": [],
                },
            ),
            Tool(
                name="list_games",
                description="List all active game sessions with their IDs and metadata.",
                inputSchema={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            Tool(
                name="get_game_state",
                description=(
                    "Return the current game state for a session as structured text. "
                    "Includes all card groups, card properties, player state, and phase info."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID returned by create_game",
                        }
                    },
                    "required": ["session_id"],
                },
            ),
            Tool(
                name="execute_action",
                description=(
                    "Execute a game action on the specified session and return the resulting state. "
                    "Supported action types: move_card, draw_card, next_step, prev_step, "
                    "set_card_property, raw."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID",
                        },
                        "action": {
                            "type": "object",
                            "description": (
                                "The action to execute. Must have a 'type' field. "
                                "Examples: "
                                '{"type": "draw_card", "player_n": "player1", "count": 1}, '
                                '{"type": "next_step"}, '
                                '{"type": "move_card", "card_id": "...", "dest_group_id": "..."}, '
                                '{"type": "raw", "action_list": ["NEXT_STEP"]}'
                            ),
                        },
                    },
                    "required": ["session_id", "action"],
                },
            ),
            Tool(
                name="delete_game",
                description="End a game session and close the WebSocket connection.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "The session ID to delete",
                        }
                    },
                    "required": ["session_id"],
                },
            ),
        ]

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    @server.call_tool()
    async def call_tool(
        name: str, arguments: dict
    ) -> list[TextContent | EmbeddedResource]:
        return await _dispatch_tool(name, arguments, session_manager)

    # ------------------------------------------------------------------
    # Resource definitions
    # ------------------------------------------------------------------

    @server.list_resources()
    async def list_resources() -> list[Resource]:
        """List available game state resources for all active sessions."""
        sessions = session_manager.list_sessions()
        return [
            Resource(
                uri=f"game://{s['session_id']}/state",
                name=f"Game state: {s['session_id']}",
                description=f"Current state for {s['plugin_name']} session {s['session_id']}",
                mimeType="application/json",
            )
            for s in sessions
        ]

    @server.read_resource()
    async def read_resource(uri) -> list[ReadResourceContents]:
        # Parse game://{session_id}/state
        # The MCP library may pass uri as an AnyUrl object; coerce to str for parsing.
        uri_str = str(uri)
        if not uri_str.startswith("game://") or not uri_str.endswith("/state"):
            raise ValueError(f"Unknown resource URI: {uri_str}")
        session_id = uri_str[len("game://") : -len("/state")]
        session = await session_manager.get_session(session_id)
        state = await session.get_state()
        content = json.dumps(state, indent=2) if state is not None else "null"
        return [ReadResourceContents(content=content, mime_type="application/json")]

    return server


# ---------------------------------------------------------------------------
# Tool dispatch (separate function for testability)
# ---------------------------------------------------------------------------


async def _dispatch_tool(
    name: str,
    arguments: dict,
    manager: SessionManager,
) -> list[TextContent]:
    """
    Dispatch an MCP tool call and return text content results.

    All errors (session not found, invalid input, etc.) are caught and
    returned as error text rather than raised, matching MCP client expectations.
    """
    try:
        return await _dispatch_tool_inner(name, arguments, manager)
    except SessionNotFoundError as exc:
        return [TextContent(type="text", text=f"Error (not found): {exc}")]
    except SessionError as exc:
        return [TextContent(type="text", text=f"Error (session): {exc}")]
    except ValueError as exc:
        return [TextContent(type="text", text=f"Error (invalid input): {exc}")]
    except Exception as exc:
        logger.exception("Unexpected error in tool %s", name)
        return [TextContent(type="text", text=f"Error (unexpected): {exc}")]


async def _dispatch_tool_inner(
    name: str,
    arguments: dict,
    manager: SessionManager,
) -> list[TextContent]:
    if name == "create_game":
        plugin_name = arguments.get("plugin_name", "marvel-champions")
        session = await manager.create_session(plugin_name)
        meta = session.to_metadata()
        result = json.dumps(meta, indent=2)
        return [TextContent(type="text", text=f"Game session created:\n{result}")]

    if name == "list_games":
        sessions = manager.list_sessions()
        if not sessions:
            return [TextContent(type="text", text="No active game sessions.")]
        result = json.dumps(sessions, indent=2)
        return [TextContent(type="text", text=f"Active sessions:\n{result}")]

    if name == "get_game_state":
        session_id = arguments["session_id"]
        session = await manager.get_session(session_id)
        state = await session.get_state()
        text = _format_state_for_llm(session_id, state)
        return [TextContent(type="text", text=text)]

    if name == "execute_action":
        session_id = arguments["session_id"]
        action_data = arguments["action"]
        action = _action_from_dict(action_data)
        session = await manager.get_session(session_id)
        new_state = await session.execute_action(action)
        text = _format_state_for_llm(session_id, new_state)
        return [TextContent(type="text", text=f"Action executed. New state:\n{text}")]

    if name == "delete_game":
        session_id = arguments["session_id"]
        await manager.delete_session(session_id)
        return [TextContent(type="text", text=f"Session {session_id} deleted.")]

    raise ValueError(f"Unknown tool: {name!r}")
