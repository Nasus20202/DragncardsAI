from __future__ import annotations

from pathlib import Path

import pytest

from agent_orchestrator.config import Settings

from ..settings_env import scrub_settings_env, settings_env_var_names
from .app_test_support import build_test_app

_SETTINGS_ENV_VAR_NAMES = settings_env_var_names(Settings)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every unit test against pristine ``Settings`` defaults.

    Unit tests take nothing from the ambient environment: a test that cares
    about a value sets it explicitly, either as a ``Settings`` keyword argument
    or with ``monkeypatch.setenv`` after this fixture has run.
    """
    scrub_settings_env(monkeypatch, _SETTINGS_ENV_VAR_NAMES)


@pytest.fixture
async def app(tmp_path: Path):
    # Deliberately does NOT honor ENABLED_PROVIDER_IDS from the environment:
    # `build_test_app` pins a fixed provider set backed by the fake Bifrost
    # client, so the unit suite behaves identically whichever providers a
    # developer has enabled. Env-driven parsing of ENABLED_PROVIDER_IDS is
    # covered directly in tests/unit/test_config.py.
    app, engine = await build_test_app(tmp_path)
    try:
        yield app
    finally:
        await engine.dispose()
