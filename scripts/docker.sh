#!/bin/bash
# Build/start/stop the repo Docker Compose stack.

set -euo pipefail

ACTION="${1:-start}"

case "$ACTION" in
    build)
        echo "Building Docker stack..."
        docker compose build
        ;;
    start)
        echo "Starting Docker stack..."
        docker compose up -d
        ;;
    stop)
        echo "Stopping Docker stack..."
        docker compose stop
        ;;
    down)
        echo "Tearing down Docker stack..."
        docker compose down -v
        ;;
    restart)
        echo "Restarting Docker stack..."
        docker compose restart
        ;;
    *)
        echo "Usage: $0 {build|start|stop|down|restart}"
        exit 1
        ;;
esac
