"""This service's own MCP surface, for a coding agent driving the dev loop.

Exposes the recorded event store as MCP tools so a coding agent can list recorded
games, read a game's ordered events and its timeline, inspect snapshots, and
restore a session to a past moment — the "analyse the agent's actions" half of the
debug loop.

Tools are generated from the FastAPI OpenAPI schema by
:mod:`dragncards_common.mcp`; the only thing declared here is what is kept out.
"""

from __future__ import annotations

from typing import Any

from dragncards_common.mcp import ExcludedRoute, mount_mcp_server

MCP_SERVER_NAME = "history-service"

#: Routes deliberately absent from this service's MCP surface. Every one stays
#: available over HTTP; see the module docstring in `dragncards_common.mcp` for
#: why each class of route is excluded.
EXCLUDED_ROUTES: tuple[ExcludedRoute, ...] = (
    # Irreversible: drops every recorded event and snapshot for a game. The
    # event store is the only durable record of what an agent did, so losing one
    # game's history destroys the evidence a debugging loop exists to read.
    (r"^/games/[^/]+$", ["DELETE"]),
    # Writes into the ordered store. Backfill and bundle import are the restore
    # and migration paths; an LLM inventing events would corrupt the record
    # while every read kept looking healthy.
    (r"^/games/[^/]+/events$", ["POST"]),
    r"^/import$",
    # Streams a whole NDJSON bundle. As a tool call it would buffer an entire
    # recorded game — hundreds of raw DragnCards states — into the caller's
    # context. Read the paged `GET /games/{game_id}/events` instead.
    r"^/games/[^/]+/export$",
)


def mount(app: Any) -> Any:
    """Mount this service's MCP transport at ``/mcp`` on ``app``."""
    return mount_mcp_server(
        app=app,
        name=MCP_SERVER_NAME,
        excluded_routes=EXCLUDED_ROUTES,
    )
