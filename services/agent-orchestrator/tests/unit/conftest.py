from __future__ import annotations

from pathlib import Path

import pytest

from .app_test_support import build_test_app


@pytest.fixture
async def app(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        yield app
    finally:
        await engine.dispose()
