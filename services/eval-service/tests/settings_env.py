"""Helpers that stop ambient service configuration from leaking into tests.

``pydantic-settings`` reads *every* ``Settings`` field from the process
environment. A developer who points the judge at whichever provider they hold a
key for (``EVAL_JUDGE_MODEL`` / ``EVAL_JUDGE_PROVIDER``), or who exports the rest
of this service's configuration (for example by sourcing ``.env``, or via
``uv run --env-file`` as ``scripts/test.sh`` does for integration runs), would
otherwise change what the tests observe. Tests
must assert on behaviour, not on the machine they run on, so each suite scrubs
the settings-derived environment and pins whatever it actually needs.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

import pytest
from pydantic import AliasChoices
from pydantic_settings import BaseSettings


def settings_env_var_names(model: type[BaseSettings]) -> frozenset[str]:
    """Every environment variable name ``model`` can read a field from.

    Derived from the model itself (field names plus declared validation aliases)
    so the scrubbing below cannot drift as settings are added.
    """
    names: set[str] = set()
    for field_name, field in model.model_fields.items():
        names.add(field_name.upper())
        alias = field.validation_alias
        if isinstance(alias, str):
            names.add(alias.upper())
        elif isinstance(alias, AliasChoices):
            names.update(
                choice.upper() for choice in alias.choices if isinstance(choice, str)
            )
    return frozenset(names)


def scrub_settings_env(
    monkeypatch: pytest.MonkeyPatch,
    names: Iterable[str],
    *,
    keep: Iterable[str] = (),
) -> None:
    """Remove settings-derived variables from the environment for one test.

    ``keep`` names the variables a suite legitimately takes from the
    environment; everything else falls back to its declared default so tests see
    the same configuration on every machine.
    """
    scrubbed = {name.upper() for name in names} - {name.upper() for name in keep}
    # Settings matching is case-insensitive, so drop any casing of a known name.
    for key in list(os.environ):
        if key.upper() in scrubbed:
            monkeypatch.delenv(key, raising=False)
