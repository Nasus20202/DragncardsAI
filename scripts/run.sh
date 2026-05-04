#!/bin/bash
# Start/stop one or more local services directly (no docker).

set -euo pipefail

ACTION="${1:-start}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/scripts/service-helpers.sh"


SERVICES=("${@:2}")
if [ "${#SERVICES[@]}" -eq 0 ]; then
    while IFS= read -r service; do
        [ -n "$service" ] && SERVICES+=("$service")
    done < <(list_services)
fi

for service in "${SERVICES[@]}"; do
    validate_service "$ROOT_DIR" "$service"
done

case "$ACTION" in
    start)
        pids=()
        cleanup() {
            local status=$?
            trap - EXIT INT TERM
            if [ "${#pids[@]}" -gt 0 ]; then
                kill "${pids[@]}" 2>/dev/null || true
            fi
            exit "$status"
        }
        trap cleanup EXIT INT TERM

        for service in "${SERVICES[@]}"; do
            start_command="$(service_start_command "$ROOT_DIR" "$service")"
            echo "Starting $service..."
            (
                eval "$start_command"
            ) &
            pids+=("$!")
        done

        wait "${pids[@]}"
        ;;
    stop)
        for service in "${SERVICES[@]}"; do
            port="$(service_http_port "$service")"
            echo "Stopping $service on port $port..."
            pid="$(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
            if [ -n "$pid" ]; then
                kill $pid
                echo "Stopped process $pid"
            else
                echo "No process found on port $port"
            fi
        done
        ;;
    *)
        echo "Usage: $0 {start|stop} [service ...]"
        exit 1
        ;;
esac
