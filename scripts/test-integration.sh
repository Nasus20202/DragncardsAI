#!/bin/bash
# Run integration tests (requires infrastructure running)

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT_DIR/services/game-service/.env"

echo ">>> Running integration tests (game-service)..."
cd "$ROOT_DIR/services/game-service" && uv run pytest tests/integration/ -v