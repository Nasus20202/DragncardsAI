"""This service's own MCP surface, for a coding agent driving the dev loop.

Exposes the judge as MCP tools so a coding agent can list the rounds detected for
a recorded game, request an evaluation of a selection of them, poll the request
until it finishes, and read the verdicts — the last two steps of the debug loop.

Tools are generated from the FastAPI OpenAPI schema by
:mod:`dragncards_common.mcp`; the only thing declared here is what is kept out.
"""

from __future__ import annotations

from typing import Any

from dragncards_common.mcp import ExcludedRoute, mount_mcp_server

MCP_SERVER_NAME = "eval-service"

#: Routes deliberately absent from this service's MCP surface. Every one stays
#: available over HTTP; see the module docstring in `dragncards_common.mcp` for
#: why each class of route is excluded.
EXCLUDED_ROUTES: tuple[ExcludedRoute, ...] = (
    # Server-sent events. A tool call reads its response to completion and this
    # one only completes when the run does; poll
    # `GET /games/{game_id}/evaluations/{request_id}` instead, which reports
    # per-target status and live error detail.
    r"^/games/[^/]+/evaluations/[^/]+/stream$",
    # An unscoped bulk delete: it drops every fully-terminal request in the
    # deployment, not only the caller's, so an agent tidying up after itself
    # would take the owner's completed verdict queue with it. (Running requests
    # survive, and history write-backs are never touched.) `delete_evaluation`
    # for one request by id stays exposed, which is all self-cleanup needs.
    r"^/evaluations/clear$",
)


def mount(app: Any) -> Any:
    """Mount this service's MCP transport at ``/mcp`` on ``app``."""
    return mount_mcp_server(
        app=app,
        name=MCP_SERVER_NAME,
        excluded_routes=EXCLUDED_ROUTES,
    )
