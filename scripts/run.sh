#!/bin/bash
# Start/stop game-service directly (no docker)

set -e

ACTION="${1:-start}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

source "$ROOT_DIR/services/game-service/.env"

case "$ACTION" in
    start)
        echo "Starting game-service..."
        cd "$ROOT_DIR/services/game-service" && uv run --env-file .env game-service
        ;;
    stop)
        echo "Stopping game-service..."
        PID=$(lsof -t -i:8000 2>/dev/null || true)
        if [ -n "$PID" ]; then
            kill "$PID"
            echo "Stopped process $PID"
        else
            echo "No process found on port 8000"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop}"
        exit 1
        ;;
esac