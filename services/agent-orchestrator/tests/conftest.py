from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest


_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5441/agent_orchestrator",
)
_postgres_available: bool | None = None


def _check_postgres() -> bool:
    global _postgres_available
    if _postgres_available is not None:
        return _postgres_available
    http_style = _DATABASE_URL.startswith("postgresql")
    if not http_style:
        _postgres_available = True
        return True
    try:
        parsed = urlparse(_DATABASE_URL.replace("+asyncpg", ""))
        hostname = parsed.hostname or "localhost"
        port = parsed.port or 5432
        with socket.create_connection((hostname, port), timeout=1.0):
            pass
        _postgres_available = True
    except Exception:
        _postgres_available = False
    return _postgres_available


def pytest_collection_modifyitems(config, items):
    skip_postgres = pytest.mark.skip(reason=f"PostgreSQL not reachable for {_DATABASE_URL}")
    for item in items:
        if item.get_closest_marker("postgres") and not _check_postgres():
            item.add_marker(skip_postgres)
