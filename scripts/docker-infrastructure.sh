#!/bin/bash
# Start/stop/restart infrastructure only (DragnCards, Valkey, Postgres, Bifrost,
# otel-lgtm, lmstudio-proxy), leaving the first-party application services alone.
#
# The service list is DERIVED from the compose files that define infrastructure so
# a newly added infra service is covered without editing this script: everything in
# docker-compose.infra.yaml plus external/docker/docker-compose.yaml is
# infrastructure, everything defined in docker-compose.yaml itself is an
# application service. Services behind an optional profile (the `smoke` model
# runtime) stay out of the list, because `config --services` hides them unless the
# profile is selected.

set -euo pipefail

ACTION="${1:-start}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

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
        docker compose -f "$APP_COMPOSE_FILE" up -d "${SERVICES[@]}"
        ;;
    stop)
        echo "Stopping infrastructure: ${SERVICES[*]}"
        docker compose -f "$APP_COMPOSE_FILE" stop "${SERVICES[@]}"
        ;;
    restart)
        echo "Restarting infrastructure: ${SERVICES[*]}"
        docker compose -f "$APP_COMPOSE_FILE" restart "${SERVICES[@]}"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}" >&2
        exit 1
        ;;
esac
