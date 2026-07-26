"""Shared internal library for DragnCards backend Python services.

Bundles cross-service helpers that were previously copy-pasted between
``agent-orchestrator``, ``eval-service`` and ``history-service``:

- :mod:`dragncards_common.schema_migrations` — the SQL migration runner.
- :mod:`dragncards_common.resp` — the minimal RESP / Valkey client.
- :mod:`dragncards_common.http_client` — a lazy ``httpx.AsyncClient`` base.
- :mod:`dragncards_common.bifrost` — Bifrost gateway error types + mapping.
"""

from __future__ import annotations

__all__ = [
    "schema_migrations",
    "resp",
    "http_client",
    "bifrost",
]
