from __future__ import annotations

import os
from pathlib import Path

import pytest

from .app_test_support import build_test_app


@pytest.fixture
async def app(tmp_path: Path):
    # Honor ENABLED_PROVIDER_IDS from the environment so the shared `app`
    # fixture mirrors whichever providers a deployment enables. Tests derive
    # their expectations from the app's configured providers, so they stay
    # correct regardless of which providers are enabled here.
    kwargs = {}
    enabled = os.environ.get("ENABLED_PROVIDER_IDS")
    if enabled:
        kwargs["enabled_provider_ids"] = enabled
    app, engine = await build_test_app(tmp_path, **kwargs)
    try:
        yield app
    finally:
        await engine.dispose()
