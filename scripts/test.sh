#!/bin/bash
# Run unit, integration, or all tests for one or more services.

set -euo pipefail

MODE="${1:-all}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/service-helpers.sh"

case "$MODE" in
    unit)
        LABEL="unit"
        ;;
    integration)
        LABEL="integration"
        ;;
    all)
        LABEL="all"
        ;;
    *)
        echo "Usage: $0 {unit|integration|all} [service ...]" >&2
        exit 1
        ;;
esac

SERVICES=()
while IFS= read -r service; do
    [ -n "$service" ] && SERVICES+=("$service")
done < <(resolve_services "$ROOT_DIR" "${@:2}")

if [ "${#SERVICES[@]}" -eq 0 ]; then
    echo "No services found" >&2
    exit 1
fi

for service in "${SERVICES[@]}"; do
    validate_service "$ROOT_DIR" "$service"
    test_command="$(service_test_command "$ROOT_DIR" "$service" "$MODE")"

    echo ">>> Running $LABEL tests ($service)..."
    (
        eval "$test_command"
    )
done
