"""This service's own MCP surface, for a coding agent driving the dev loop.

Not to be confused with :mod:`agent_orchestrator.integrations.mcp`, which is the
MCP *client* this service uses to hand tools to the game-playing agent. This
module is the opposite direction: it exposes this service's HTTP API as MCP tools
so a coding agent can start a player agent, submit a prompt, and read the
resulting job events without hand-rolling HTTP calls.

Tools are generated from the FastAPI OpenAPI schema by
:mod:`dragncards_common.mcp`; the only thing declared here is what is kept out.
"""

from __future__ import annotations

from typing import Any

from dragncards_common.mcp import ExcludedRoute, mount_mcp_server

MCP_SERVER_NAME = "agent-orchestrator"

#: Routes deliberately absent from this service's MCP surface. Every one stays
#: available over HTTP; see the module docstring in `dragncards_common.mcp` for
#: why each class of route is excluded.
EXCLUDED_ROUTES: tuple[ExcludedRoute, ...] = (
    # Server-sent events. A tool call reads its response to completion and this
    # one never completes; `GET /jobs/{job_id}/events` is the paged read an
    # agent should poll instead.
    r"^/jobs/[^/]+/events/stream$",
    # The skill and MCP registries are deployment-global: an entry added or
    # removed here changes what every session in the deployment resolves,
    # including the owner's. Reading them is fine, editing them is a deliberate
    # HTTP or dashboard action.
    (r"^/skills$", ["POST"]),
    r"^/skills/[^/]+$",
    (r"^/mcps$", ["POST"]),
    r"^/mcps/[^/]+$",
    # Personas are deployment-global and user-authored. A persona is captured at
    # spawn time, so editing one cannot corrupt a running subagent, but it does
    # silently change what every later spawn gets.
    (r"^/personas/[^/]+$", ["PUT", "DELETE"]),
)


def mount(app: Any) -> Any:
    """Mount this service's MCP transport at ``/mcp`` on ``app``."""
    return mount_mcp_server(
        app=app,
        name=MCP_SERVER_NAME,
        excluded_routes=EXCLUDED_ROUTES,
    )
