#!/bin/bash

# Focused checks for the profile-gated marvel-lcg infrastructure. The platform
# image is deliberately not started here; the integration owner can start it
# with `make up-marvel-lcg` after supplying a local password.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

default_services="$(docker compose config --services)"
if printf '%s\n' "$default_services" | grep -Fxq marvel-lcg; then
    printf '%s\n' 'marvel-lcg must remain hidden from the default Compose service list' >&2
    exit 1
fi

profile_services="$(MARVEL_LCG_PASSWORD=test-only docker compose --profile marvel-lcg config --services)"
if ! printf '%s\n' "$profile_services" | grep -Fxq marvel-lcg; then
    printf '%s\n' 'marvel-lcg is missing from its explicit Compose profile' >&2
    exit 1
fi

if ! grep -Fq 'MARVEL_LCG_PASSWORD must be set' external/docker/marvel-lcg/entrypoint.sh; then
    printf '%s\n' 'marvel-lcg entrypoint does not enforce its required password' >&2
    exit 1
fi

if output="$(env -u MARVEL_LCG_PASSWORD external/docker/marvel-lcg/entrypoint.sh 2>&1)"; then
    printf '%s\n' 'marvel-lcg entrypoint accepted a missing password' >&2
    exit 1
fi
if ! printf '%s\n' "$output" | grep -Fq 'MARVEL_LCG_PASSWORD must be set'; then
    printf '%s\n' "$output" >&2
    printf '%s\n' 'missing-password failure did not name MARVEL_LCG_PASSWORD' >&2
    exit 1
fi

# The platform's arbitrary-command endpoint must never be composed by a
# first-party route. The upstream submodule is intentionally excluded from this
# check because it owns that endpoint; only our application surfaces matter.
FIRST_PARTY_SOURCE=(services/game-service/src services/dashboard/app services/dashboard/features)
# The Marvel HTTP client names forbidden paths only to reject them. Exclude that
# defensive allowlist check while scanning for code that could compose a route.
SAFE_PATH_VALIDATOR=services/game-service/src/game_service/marvel_lcg/client.py
if git grep -nE "['\"]/debug|[?&](cheat|show|replay)=" -- "${FIRST_PARTY_SOURCE[@]}" ":(exclude)$SAFE_PATH_VALIDATOR" >/dev/null 2>&1; then
    printf '%s\n' 'a first-party surface contains a marvel-lcg debug/cheat URL' >&2
    git grep -nE "['\"]/debug|[?&](cheat|show|replay)=" -- "${FIRST_PARTY_SOURCE[@]}" ":(exclude)$SAFE_PATH_VALIDATOR" >&2
    exit 1
fi

printf '%s\n' 'marvel-lcg infrastructure checks passed'
