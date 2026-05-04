#!/bin/bash
# Start/stop game-service container via docker-compose

set -e

ACTION="${1:-start}"

case "$ACTION" in
    start)
        echo "Starting game-service container..."
        docker compose up game-service -d
        ;;
    stop)
        echo "Stopping game-service container..."
        docker compose stop game-service
        ;;
    restart)
        echo "Restarting game-service container..."
        docker compose restart game-service
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac