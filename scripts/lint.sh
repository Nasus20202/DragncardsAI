#!/bin/bash

set -euo pipefail

MODE="${1:-check}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

case "$MODE" in
    check|--check)
        DASHBOARD_FORMAT_CMD="pnpm format:check"
        DASHBOARD_LINT_CMD="pnpm lint"
        PYTHON_FORMAT_CMD="uv run black --check src tests"
        DASHBOARD_LABEL="Validating"
        PYTHON_LABEL="Validating"
        ;;
    fix|--fix)
        DASHBOARD_FORMAT_CMD="pnpm format"
        DASHBOARD_LINT_CMD="pnpm lint --fix"
        PYTHON_FORMAT_CMD="uv run black src tests"
        DASHBOARD_LABEL="Fixing"
        PYTHON_LABEL="Fixing"
        ;;
    *)
        echo "Usage: $0 [check|--check|fix|--fix]" >&2
        exit 1
        ;;
esac

echo ">>> $DASHBOARD_LABEL dashboard formatting and linting..."
(
    cd "$ROOT_DIR/services/dashboard"
    eval "$DASHBOARD_FORMAT_CMD"
    eval "$DASHBOARD_LINT_CMD"
    pnpm typecheck
)

for service in game-service agent-orchestrator; do
    echo ">>> $PYTHON_LABEL Python formatting ($service)..."
    (
        cd "$ROOT_DIR/services/$service"
        eval "$PYTHON_FORMAT_CMD"
    )
done
