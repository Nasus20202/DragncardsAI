#!/bin/bash
# Build/start/stop the repo Docker Compose stack.

set -euo pipefail

ACTION="${1:-start}"
SERVICES=("${@:2}")

compose_with_optional_services() {
    local action="$1"
    shift

    if [ "${#SERVICES[@]}" -gt 0 ]; then
        docker compose "$action" "$@" "${SERVICES[@]}"
    else
        docker compose "$action" "$@"
    fi
}

case "$ACTION" in
    build)
        echo "Building Docker stack..."
        compose_with_optional_services build
        ;;
    start)
        echo "Starting Docker stack..."
        if [ "${#SERVICES[@]}" -gt 0 ]; then
            compose_with_optional_services up -d --build
        else
            # A normal local start must rebuild checked-out external sources. The
            # registry workflow sets IMAGE_PULL_POLICY=always and intentionally
            # skips local builds.
            if [ "${IMAGE_PULL_POLICY:-never}" != "always" ]; then
                docker compose build dragncards-mc-plugin dragncards-backend dragncards-frontend
            fi
            # Start the coupled group first. A dependency image change alone does
            # not require-recreate its dependent backend, so force the group before
            # the application services can connect to it.
            docker compose up -d --force-recreate \
                dragncards-mc-plugin dragncards-backend dragncards-frontend
            docker compose up -d
        fi
        ;;
    stop)
        echo "Stopping Docker stack..."
        compose_with_optional_services stop
        ;;
    down)
        if [ "${#SERVICES[@]}" -gt 0 ]; then
            echo "Service arguments are not supported for 'down'" >&2
            exit 1
        fi
        echo "Tearing down Docker stack..."
        docker compose down
        ;;
    down-clean)
        if [ "${#SERVICES[@]}" -gt 0 ]; then
            echo "Service arguments are not supported for 'down-clean'" >&2
            exit 1
        fi
        echo "Tearing down Docker stack and removing volumes..."
        docker compose down -v
        ;;
    restart)
        echo "Restarting Docker stack..."
        compose_with_optional_services restart
        ;;
    *)
        echo "Usage: $0 {build|start|stop|down|down-clean|restart} [service ...]"
        exit 1
        ;;
esac
