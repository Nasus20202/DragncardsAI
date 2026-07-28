from __future__ import annotations

import pytest

from eval_service.config import Settings

from .settings_env import scrub_settings_env, settings_env_var_names

_SETTINGS_ENV_VAR_NAMES = settings_env_var_names(Settings)
# The suites build their own Settings and talk to fakes, so the only
# settings-derived variable they legitimately take from the environment is the
# PostgreSQL URL used by tests/integration/conftest.py. Everything else --
# notably the judge model/provider, which a developer points at whichever
# gateway provider they hold a key for -- is owned by the tests.
_ENV_OWNED_BY_THE_ENVIRONMENT = ("EVAL_DATABASE_URL",)


@pytest.fixture(autouse=True)
def isolated_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    scrub_settings_env(
        monkeypatch, _SETTINGS_ENV_VAR_NAMES, keep=_ENV_OWNED_BY_THE_ENVIRONMENT
    )
