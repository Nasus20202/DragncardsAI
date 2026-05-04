#!/bin/bash
# Start/stop infrastructure (dragncards-backend, database, etc.)

set -e

ACTION="${1:-start}"

INFRA_SERVICES="dragncards-backend dragncards-frontend"

case "$ACTION" in
    start)
        echo "Starting infrastructure..."
        docker compose up -d $INFRA_SERVICES
        ;;
    stop)
        echo "Stopping infrastructure..."
        docker compose stop $INFRA_SERVICES
        ;;
    restart)
        echo "Restarting infrastructure..."
        docker compose restart $INFRA_SERVICES
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
        ;;
esac