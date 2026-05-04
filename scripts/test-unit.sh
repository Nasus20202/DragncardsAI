#!/bin/bash
# Run unit tests (no network required)

set -e

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo ">>> Running unit tests (game-service)..."
cd "$ROOT_DIR/services/game-service" && uv run pytest tests/unit/ -v