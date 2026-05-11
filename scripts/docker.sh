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
        compose_with_optional_services up -d
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
