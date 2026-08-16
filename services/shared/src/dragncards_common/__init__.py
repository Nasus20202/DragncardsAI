"""Shared internal library for DragnCards backend Python services.

Bundles cross-service helpers that were previously copy-pasted between
``agent-orchestrator``, ``eval-service`` and ``history-service``:

- :mod:`dragncards_common.schema_migrations` — the SQL migration runner.
- :mod:`dragncards_common.resp` — the minimal RESP / Valkey client.
- :mod:`dragncards_common.http_client` — a lazy ``httpx.AsyncClient`` base.
- :mod:`dragncards_common.bifrost` — Bifrost gateway error types + mapping.
- :mod:`dragncards_common.telemetry` — the OpenTelemetry bootstrap.
- :mod:`dragncards_common.mcp` — the MCP surface derived from a service's own
  OpenAPI schema, so a coding agent can drive every service over MCP and not
  only ``game-service``.
- :mod:`dragncards_common.capabilities` — the ``GET /capabilities`` payload,
  whose feature list is derived from the app's own OpenAPI document so a client
  can detect version skew before it sends anything.
"""

from __future__ import annotations

__all__ = [
    "schema_migrations",
    "resp",
    "http_client",
    "bifrost",
    "telemetry",
    "mcp",
    "capabilities",
]
