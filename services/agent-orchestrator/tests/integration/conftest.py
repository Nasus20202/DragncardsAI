from __future__ import annotations

from pathlib import Path

import pytest

from agent_orchestrator.config import Settings

from ..settings_env import scrub_settings_env, settings_env_var_names
from .api_test_support import (
    UnreachableLiveEventBus,
    build_integration_app,
    build_real_mcp_app,
)

_SETTINGS_ENV_VAR_NAMES = settings_env_var_names(Settings)
# The integration suite builds its apps in-process against fakes, so the only
# settings-derived variable it legitimately takes from the environment is the
# PostgreSQL URL used by tests/integration/test_postgres_repository.py. Every
# other value (provider set, worker limits, default MCP wiring, context budget)
# is owned by the harness, so a developer's `.env` cannot change the outcome.
# `scripts/test.sh integration` runs under `uv run --env-file <service>/.env`,
# which is exactly how a narrowed provider list used to leak in here.
_ENV_OWNED_BY_THE_ENVIRONMENT = ("DATABASE_URL",)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    scrub_settings_env(
        monkeypatch, _SETTINGS_ENV_VAR_NAMES, keep=_ENV_OWNED_BY_THE_ENVIRONMENT
    )


@pytest.fixture
async def app(tmp_path: Path):
    app, engine = await build_integration_app(tmp_path)
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.fixture
async def unreachable_live_bus_app(tmp_path: Path):
    """The integration app with a live event bus that fails every operation."""
    app, engine = await build_integration_app(
        tmp_path, live_event_bus=UnreachableLiveEventBus()
    )
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()


@pytest.fixture
async def real_mcp_app(tmp_path: Path):
    app, engine = await build_real_mcp_app(tmp_path)
    async with app.router.lifespan_context(app):
        yield app
    await engine.dispose()
