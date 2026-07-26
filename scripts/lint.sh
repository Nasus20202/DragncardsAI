#!/bin/bash

set -euo pipefail

MODE="${1:-check}"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

case "$MODE" in
    check|--check)
        DASHBOARD_FORMAT_CMD="pnpm format:check"
        DASHBOARD_LINT_CMD="pnpm lint"
        SMOKETEST_FORMAT_CMD="pnpm format:check"
        PYTHON_FORMAT_CMD="uv run black --check src tests"
        JS_LABEL="Validating"
        PYTHON_LABEL="Validating"
        ;;
    fix|--fix)
        DASHBOARD_FORMAT_CMD="pnpm format"
        DASHBOARD_LINT_CMD="pnpm lint --fix"
        SMOKETEST_FORMAT_CMD="pnpm format"
        PYTHON_FORMAT_CMD="uv run black src tests"
        JS_LABEL="Fixing"
        PYTHON_LABEL="Fixing"
        ;;
    *)
        echo "Usage: $0 [check|--check|fix|--fix]" >&2
        exit 1
        ;;
esac

echo ">>> $JS_LABEL dashboard formatting and linting..."
(
    cd "$ROOT_DIR/services/dashboard"
    eval "$DASHBOARD_FORMAT_CMD"
    eval "$DASHBOARD_LINT_CMD"
    pnpm typecheck
)

echo ">>> $JS_LABEL smoketest formatting..."
(
    cd "$ROOT_DIR/services/smoketest"
    eval "$SMOKETEST_FORMAT_CMD"
    pnpm typecheck
)

for service in shared game-service agent-orchestrator history-service eval-service; do
    echo ">>> $PYTHON_LABEL Python formatting ($service)..."
    (
        cd "$ROOT_DIR/services/$service"
        eval "$PYTHON_FORMAT_CMD"
    )
done
