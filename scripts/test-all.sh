#!/bin/bash
# Run all tests (unit + integration)

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/services/game-service/.env"

echo ">>> Running all tests (game-service)..."
cd "$ROOT_DIR/services/game-service" && uv run pytest tests/ -v