"""Shared MCP-surface bootstrap for the first-party Python services.

A coding agent debugging this repository drives the whole loop — create a game,
start a player agent, read the agent's actions, read live board state, request an
evaluation, read the verdict — across four services. Only ``game-service`` used
to be reachable over MCP, so two thirds of that loop had to be hand-rolled as
``curl`` calls against endpoints the agent had to guess the shape of. This module
gives ``agent-orchestrator``, ``history-service`` and ``eval-service`` the same
MCP surface ``game-service`` already has.

**Tools are derived from the service's own OpenAPI schema, never hand-written.**
``FastMCP.from_fastapi`` reads the FastAPI app the service already builds, so
every MCP tool is the HTTP endpoint it was generated from, with the endpoint's
own request and response models as its schema. A hand-written tool layer would be
a second implementation of the API that drifts from the first one; there is no
mechanism here to add a tool that is not an endpoint, and there should not be.

**The exclusion list is the whole security surface.** These services carry no
authentication — they are reachable on localhost and, in Compose, on the internal
network — so anything left in the MCP surface is something an LLM can invoke on a
running deployment with no further check. Each service therefore passes the
routes it will not expose, and three kinds are always kept out:

- **Liveness and readiness probes**, excluded here for every service: an LLM
  client gains nothing from them and they crowd the tool list.
- **Streaming responses** (server-sent events). An MCP tool call reads a
  response to completion, and an SSE endpoint deliberately does not complete, so
  a streaming route mapped to a tool hangs the caller until it times out. The
  paged read alongside it (``GET /jobs/{id}/events``) is the surface to use.
- **Irreversible destruction and deployment-global mutation** — deleting a game's
  recorded history, bulk-clearing the evaluation queue, editing the shared MCP
  registry. ``game-service`` set this precedent by excluding its snapshot
  import/export, room-control and raw-DragnLang routes from MCP while keeping
  them on HTTP: the operation stays available to a developer who types it
  deliberately, and is not offered to a model as a tool.

Excluding a route removes it from MCP only. The HTTP endpoint is untouched, so
nothing here reduces what the dashboard or a human with ``curl`` can do.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap
from fastmcp.utilities.lifespan import combine_lifespans

logger = logging.getLogger(__name__)

#: Where every service mounts its streamable-HTTP MCP transport. Clients address
#: it with a trailing slash (``http://localhost:4002/mcp/``).
MCP_MOUNT_PATH = "/mcp"

#: Excluded for every service: probes are noise in an LLM's tool list.
ALWAYS_EXCLUDED_ROUTES: tuple[str, ...] = (r"^/health$", r"^/ready$")

#: A route to keep out of the MCP surface: either a path-regex on its own (all
#: methods) or ``(path_regex, methods)`` to exclude only some verbs — needed
#: wherever one path is a safe read and an unsafe write, as
#: ``/games/{game_id}/events`` is on history-service.
ExcludedRoute = str | tuple[str, Sequence[str]]


def _route_maps(excluded_routes: Sequence[ExcludedRoute]) -> list[RouteMap]:
    maps: list[RouteMap] = []
    for entry in (*ALWAYS_EXCLUDED_ROUTES, *excluded_routes):
        if isinstance(entry, str):
            maps.append(RouteMap(pattern=entry, mcp_type=MCPType.EXCLUDE))
            continue
        pattern, methods = entry
        maps.append(
            RouteMap(
                pattern=pattern,
                methods=list(methods),
                mcp_type=MCPType.EXCLUDE,
            )
        )
    return maps


def build_mcp_server(
    *,
    app: Any,
    name: str,
    excluded_routes: Sequence[ExcludedRoute] = (),
) -> FastMCP:
    """Build the MCP server for ``app``, minus ``excluded_routes``.

    ``app`` is the service's own FastAPI application; ``name`` is the MCP server
    name a client sees, which by convention is the service name.
    """
    route_maps = _route_maps(excluded_routes)
    logger.info(
        "Building MCP server %s from OpenAPI schema (%d excluded route rules)",
        name,
        len(route_maps),
    )
    return FastMCP.from_fastapi(app=app, name=name, route_maps=route_maps)


def mount_mcp_server(
    *,
    app: Any,
    name: str,
    excluded_routes: Sequence[ExcludedRoute] = (),
    path: str = MCP_MOUNT_PATH,
) -> FastMCP:
    """Build the MCP server and mount its streamable-HTTP transport on ``app``.

    Call this from the service's entrypoint on the app the app factory returned,
    not inside the factory: the factory is what the test suites instantiate, and
    they neither need the MCP transport nor should pay for starting its session
    manager.

    The MCP session manager has its own lifespan and will not run unless it is
    started, so the app's existing lifespan is wrapped with
    ``combine_lifespans`` rather than replaced — both come up and shut down
    together.
    """
    mcp = build_mcp_server(app=app, name=name, excluded_routes=excluded_routes)
    mcp_asgi = mcp.http_app(path="/")
    app.router.lifespan_context = combine_lifespans(
        app.router.lifespan_context, mcp_asgi.lifespan
    )
    app.mount(path, mcp_asgi)
    logger.info("Mounted MCP server %s at %s", name, path)
    return mcp
