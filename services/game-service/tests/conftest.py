"""
Root test configuration.

Provides the `live` pytest mark. Tests decorated with @pytest.mark.live require
a running DragnCards backend and are skipped automatically when the backend is
unreachable. Set DRAGNCARDS_HTTP_URL to override the default localhost:4000.

To force-run live tests against a running backend:
    uv run python -m pytest tests/integration/ -v
"""

from __future__ import annotations

import os

import httpx
import pytest


_DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
_backend_available: bool | None = None


def _check_backend() -> bool:
    global _backend_available
    if _backend_available is not None:
        return _backend_available
    try:
        with httpx.Client(timeout=2.0) as client:
            client.get(_DRAGNCARDS_HTTP_URL)
        _backend_available = True
    except Exception:
        _backend_available = False
    return _backend_available


def pytest_collection_modifyitems(config, items):
    """Auto-skip `live` tests when the DragnCards backend is unreachable."""
    skip_live = pytest.mark.skip(
        reason=f"DragnCards backend not reachable at {_DRAGNCARDS_HTTP_URL} (mark test with @pytest.mark.live)"
    )
    for item in items:
        if item.get_closest_marker("live") and not _check_backend():
            item.add_marker(skip_live)
