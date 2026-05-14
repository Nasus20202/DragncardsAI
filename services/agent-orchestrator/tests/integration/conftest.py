from __future__ import annotations

from pathlib import Path

import pytest

from .api_test_support import build_integration_app, build_real_mcp_app


@pytest.fixture
async def app(tmp_path: Path):
    app, engine = await build_integration_app(tmp_path)
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.fixture
async def real_mcp_app(tmp_path: Path):
    app, engine = await build_real_mcp_app(tmp_path)
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()
