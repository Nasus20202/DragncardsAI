#!/bin/bash
# Start/stop infrastructure (Valkey and DragnCards services)

set -e

ACTION="${1:-start}"

INFRA_SERVICES="dragncards-backend dragncards-frontend"
INFRA_COMPOSE_FILE="docker-compose.infra.yaml"
APP_COMPOSE_FILE="docker-compose.yaml"

case "$ACTION" in
    start)
        echo "Starting infrastructure..."
        docker compose -f "$INFRA_COMPOSE_FILE" up -d game-service-valkey
        docker compose -f "$APP_COMPOSE_FILE" up -d $INFRA_SERVICES
        ;;
    stop)
        echo "Stopping infrastructure..."
        docker compose -f "$INFRA_COMPOSE_FILE" stop game-service-valkey
        docker compose -f "$APP_COMPOSE_FILE" stop $INFRA_SERVICES
        ;;
    restart)
        echo "Restarting infrastructure..."
        docker compose -f "$INFRA_COMPOSE_FILE" restart game-service-valkey
        docker compose -f "$APP_COMPOSE_FILE" restart $INFRA_SERVICES
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac
