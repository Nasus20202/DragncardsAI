from __future__ import annotations

import pytest

from history_service.config import Settings

from .settings_env import scrub_settings_env, settings_env_var_names

_SETTINGS_ENV_VAR_NAMES = settings_env_var_names(Settings)
# tests/integration/conftest.py reads these two at import time to reach the real
# PostgreSQL and Valkey; every other setting is owned by the tests, so a
# developer's `.env` cannot change what the suite observes.
_ENV_OWNED_BY_THE_ENVIRONMENT = ("HISTORY_DATABASE_URL", "VALKEY_URL")


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    scrub_settings_env(
        monkeypatch, _SETTINGS_ENV_VAR_NAMES, keep=_ENV_OWNED_BY_THE_ENVIRONMENT
    )
