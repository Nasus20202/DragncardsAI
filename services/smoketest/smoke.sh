#!/bin/bash

set -euo pipefail

ACTION="${1:-help}"
shift || true

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
SMOKETEST_DIR="$(cd "$(dirname "$0")" && pwd)"

GAME_SERVICE_HOST_PORT="${GAME_SERVICE_HOST_PORT:-4001}"
AGENT_ORCHESTRATOR_HOST_PORT="${AGENT_ORCHESTRATOR_HOST_PORT:-4002}"
DASHBOARD_HOST_PORT="${DASHBOARD_HOST_PORT:-3001}"
LLAMA_CPP_HOST_PORT="${LLAMA_CPP_HOST_PORT:-1234}"

SMOKE_MODEL_PROVIDER_ID="${SMOKE_MODEL_PROVIDER_ID:-lmstudio}"
SMOKE_MODEL_NAME="${SMOKE_MODEL_NAME:-qwen3.5-0.8b}"
LLAMA_CPP_MODEL_FILE="${LLAMA_CPP_MODEL_FILE:-Qwen3.5-0.8B-Q4_K_M.gguf}"
LLAMA_CPP_MODEL_URL="${LLAMA_CPP_MODEL_URL:-https://huggingface.co/lmstudio-community/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_K_M.gguf?download=1}"
LLAMA_CPP_MODEL_CACHE_DIR="${LLAMA_CPP_MODEL_CACHE_DIR:-$HOME/.cache/dragncardsai/llama.cpp}"
LLAMA_CPP_CTX_SIZE="${LLAMA_CPP_CTX_SIZE:-16384}"
LLAMA_CPP_N_GPU_LAYERS="${LLAMA_CPP_N_GPU_LAYERS:-0}"
LMSTUDIO_BASE_URL="${LMSTUDIO_BASE_URL:-http://llama-cpp-smoke:1234/v1}"
LLAMA_CPP_SMOKE_URL="${LLAMA_CPP_SMOKE_URL:-http://127.0.0.1:${LLAMA_CPP_HOST_PORT}/v1}"
DASHBOARD_SMOKE_BASE_URL="${DASHBOARD_SMOKE_BASE_URL:-http://127.0.0.1:${DASHBOARD_HOST_PORT}}"
AGENT_ORCHESTRATOR_SMOKE_URL="${AGENT_ORCHESTRATOR_SMOKE_URL:-http://127.0.0.1:${AGENT_ORCHESTRATOR_HOST_PORT}}"
GAME_SERVICE_SMOKE_URL="${GAME_SERVICE_SMOKE_URL:-http://127.0.0.1:${GAME_SERVICE_HOST_PORT}}"
ENABLED_PROVIDER_IDS="${ENABLED_PROVIDER_IDS:-lmstudio}"
DEFAULT_PROVIDER_ID="${DEFAULT_PROVIDER_ID:-$SMOKE_MODEL_PROVIDER_ID}"
DEFAULT_MODEL_NAME="${DEFAULT_MODEL_NAME:-$SMOKE_MODEL_NAME}"
SMOKE_CHECK_RETRIES="${SMOKE_CHECK_RETRIES:-60}"
SMOKE_CHECK_INTERVAL_SECONDS="${SMOKE_CHECK_INTERVAL_SECONDS:-2}"

check_url() {
    local url="$1"
    local label="$2"

    local attempt
    for attempt in $(seq 1 "$SMOKE_CHECK_RETRIES"); do
        if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep "$SMOKE_CHECK_INTERVAL_SECONDS"
    done

    echo "Smoke dependency unavailable: $label ($url)" >&2
    exit 1
}

case "$ACTION" in
    up)
        echo "Starting Docker stack with smoke-model defaults..."
        export SMOKE_MODEL_PROVIDER_ID
        export SMOKE_MODEL_NAME
        export LLAMA_CPP_MODEL_FILE
        export LLAMA_CPP_MODEL_URL
        export LLAMA_CPP_MODEL_CACHE_DIR
        export LLAMA_CPP_CTX_SIZE
        export LLAMA_CPP_N_GPU_LAYERS
        export LMSTUDIO_BASE_URL
        export ENABLED_PROVIDER_IDS
        export DEFAULT_PROVIDER_ID
        export DEFAULT_MODEL_NAME
        export GAME_SERVICE_HOST_PORT
        export AGENT_ORCHESTRATOR_HOST_PORT
        export DASHBOARD_HOST_PORT
        export LLAMA_CPP_HOST_PORT
        if [ "$#" -gt 0 ]; then
            docker compose --profile smoke up -d llama-cpp-smoke
            docker compose --profile smoke up -d "$@"
        else
            docker compose --profile smoke up -d
        fi
        ;;
    check)
        echo "Checking smoke dependencies..."
        check_url "$LLAMA_CPP_SMOKE_URL/models" "llama.cpp smoke model"
        check_url "$AGENT_ORCHESTRATOR_SMOKE_URL/health" "agent-orchestrator"
        check_url "$GAME_SERVICE_SMOKE_URL/health" "game-service"
        check_url "$DASHBOARD_SMOKE_BASE_URL/api/config" "dashboard"
        echo "Smoke dependencies are reachable."
        ;;
    model)
        export SMOKE_MODEL_NAME
        export LLAMA_CPP_MODEL_FILE
        export LLAMA_CPP_MODEL_URL
        export LLAMA_CPP_MODEL_CACHE_DIR
        export LLAMA_CPP_CTX_SIZE
        export LLAMA_CPP_N_GPU_LAYERS
        export LLAMA_CPP_HOST_PORT
        exec docker compose --profile smoke up -d llama-cpp-smoke
        ;;
    test)
        "$SMOKETEST_DIR/smoke.sh" check
        export SMOKE_MODEL_PROVIDER_ID
        export SMOKE_MODEL_NAME
        export LLAMA_CPP_SMOKE_URL
        export DASHBOARD_SMOKE_BASE_URL
        export AGENT_ORCHESTRATOR_SMOKE_URL
        export GAME_SERVICE_SMOKE_URL
        cd "$SMOKETEST_DIR"
        exec pnpm test -- "$@"
        ;;
    *)
        echo "Usage: $0 {up [service ...]|check|model|test [playwright args ...]}" >&2
        exit 1
        ;;
esac
