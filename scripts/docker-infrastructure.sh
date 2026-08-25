#!/bin/bash
# Start/stop/restart infrastructure only (DragnCards, Valkey, Postgres, Bifrost,
# otel-lgtm, lmstudio-proxy), leaving the first-party application services alone.
# Start and restart wait for bounded Compose readiness. Restart removes the
# one-shot Marvel initializer so it is recreated before the engine starts again.
#
# The service list is DERIVED from the compose files that define infrastructure so
# a newly added infra service is covered without editing this script: everything in
# docker-compose.infra.yaml plus external/docker/docker-compose.yaml is
# infrastructure, everything defined in docker-compose.yaml itself is an
# application service. The ordinary marvel-lcg backend and its initializer are
# included because they are no longer behind a Compose profile. The optional
# smoke model remains intentionally outside this lifecycle.

set -euo pipefail

ACTION="${1:-start}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MARVEL_LCG_WAIT_TIMEOUT_SECONDS="${MARVEL_LCG_WAIT_TIMEOUT_SECONDS:-300}"

if ! [[ "$MARVEL_LCG_WAIT_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
    echo "MARVEL_LCG_WAIT_TIMEOUT_SECONDS must be a positive integer" >&2
    exit 1
fi

APP_COMPOSE_FILE="docker-compose.yaml"
INFRA_COMPOSE_FILES=("docker-compose.infra.yaml" "external/docker/docker-compose.yaml")

cd "$ROOT_DIR"

infra_services() {
    local compose_file
    for compose_file in "${INFRA_COMPOSE_FILES[@]}"; do
        docker compose -f "$compose_file" config --services
    done | sort -u
}

SERVICES=()
while IFS= read -r service; do
    [ -n "$service" ] && SERVICES+=("$service")
done < <(infra_services)

if [ "${#SERVICES[@]}" -eq 0 ]; then
    echo "No infrastructure services found" >&2
    exit 1
fi

# Act through docker-compose.yaml (which `include:`s the infra files) so the
# commands target the combined project the full stack actually runs under.
case "$ACTION" in
    start)
        echo "Starting infrastructure: ${SERVICES[*]}"
        docker compose -f "$APP_COMPOSE_FILE" up -d \
            --wait --wait-timeout "$MARVEL_LCG_WAIT_TIMEOUT_SECONDS" "${SERVICES[@]}"
        ;;
    stop)
        echo "Stopping infrastructure: ${SERVICES[*]}"
        docker compose -f "$APP_COMPOSE_FILE" stop "${SERVICES[@]}"
        ;;
    restart)
        echo "Restarting infrastructure: ${SERVICES[*]}"
        docker compose -f "$APP_COMPOSE_FILE" stop "${SERVICES[@]}"
        docker compose -f "$APP_COMPOSE_FILE" rm -f -s marvel-lcg-init
        docker compose -f "$APP_COMPOSE_FILE" up -d \
            --wait --wait-timeout "$MARVEL_LCG_WAIT_TIMEOUT_SECONDS" "${SERVICES[@]}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}" >&2
        exit 1
        ;;
esac
