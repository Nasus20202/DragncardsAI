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

prepare_game_service_environment() {
    # A source game-service process needs the same password as the healthy
    # Docker engine started by docker-infrastructure.sh. Prefer an explicitly
    # exported source value; otherwise copy only the engine's configured value
    # from its container environment without printing it or writing it down.
    if [ -n "${MARVEL_LCG_PASSWORD:-}" ] || ! command -v docker >/dev/null 2>&1; then
        return 0
    fi

    local engine_id engine_health engine_password
    engine_id="$(docker compose -f "$ROOT_DIR/docker-compose.yaml" ps -q marvel-lcg 2>/dev/null || true)"
    [ -n "$engine_id" ] || return 0

    engine_health="$(docker inspect -f '{{.State.Health.Status}}' "$engine_id" 2>/dev/null || true)"
    [ "$engine_health" = "healthy" ] || return 0

    engine_password="$(
        docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$engine_id" 2>/dev/null |
            python3 -c '
import sys
for line in sys.stdin:
    key, separator, value = line.rstrip("\n").partition("=")
    if key == "MARVEL_LCG_PASSWORD" and separator:
        print(value, end="")
        break
'
    )"
    if [ -n "$engine_password" ]; then
        export MARVEL_LCG_PASSWORD="$engine_password"
        echo "Using the healthy Docker marvel-lcg password for source game-service startup."
    fi
}

case "$ACTION" in
    start)
        if printf '%s\n' "${SERVICES[@]}" | grep -Fxq game-service; then
            prepare_game_service_environment
        fi

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
