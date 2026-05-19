#!/bin/bash

set -euo pipefail

ACTION="${1:-help}"
shift || true

SMOKETEST_DIR="$(cd "$(dirname "$0")" && pwd)"

export GAME_SERVICE_HOST_PORT="${GAME_SERVICE_HOST_PORT:-4001}"
export AGENT_ORCHESTRATOR_HOST_PORT="${AGENT_ORCHESTRATOR_HOST_PORT:-4002}"
export DASHBOARD_HOST_PORT="${DASHBOARD_HOST_PORT:-3001}"
export LLAMA_CPP_HOST_PORT="${LLAMA_CPP_HOST_PORT:-1234}"

export SMOKE_MODEL_PROVIDER_ID="${SMOKE_MODEL_PROVIDER_ID:-lmstudio}"
export SMOKE_MODEL_NAME="${SMOKE_MODEL_NAME:-qwen3.5-0.8b}"
export LLAMA_CPP_MODEL_FILE="${LLAMA_CPP_MODEL_FILE:-Qwen3.5-0.8B-Q4_K_M.gguf}"
export LLAMA_CPP_MODEL_URL="${LLAMA_CPP_MODEL_URL:-https://huggingface.co/lmstudio-community/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_K_M.gguf?download=1}"
export LLAMA_CPP_MODEL_CACHE_DIR="${LLAMA_CPP_MODEL_CACHE_DIR:-$HOME/.cache/dragncardsai/llama.cpp}"
export LLAMA_CPP_CTX_SIZE="${LLAMA_CPP_CTX_SIZE:-16384}"
export LLAMA_CPP_N_GPU_LAYERS="${LLAMA_CPP_N_GPU_LAYERS:-0}"
export LLAMA_CPP_PARALLEL="${LLAMA_CPP_PARALLEL:-1}"
export LMSTUDIO_BASE_URL="${LMSTUDIO_BASE_URL:-http://llama-cpp-smoke:1234/v1}"
export LLAMA_CPP_SMOKE_URL="${LLAMA_CPP_SMOKE_URL:-http://127.0.0.1:${LLAMA_CPP_HOST_PORT}/v1}"
export DASHBOARD_SMOKE_BASE_URL="${DASHBOARD_SMOKE_BASE_URL:-http://127.0.0.1:${DASHBOARD_HOST_PORT}}"
export AGENT_ORCHESTRATOR_SMOKE_URL="${AGENT_ORCHESTRATOR_SMOKE_URL:-http://127.0.0.1:${AGENT_ORCHESTRATOR_HOST_PORT}}"
export GAME_SERVICE_SMOKE_URL="${GAME_SERVICE_SMOKE_URL:-http://127.0.0.1:${GAME_SERVICE_HOST_PORT}}"
export ENABLED_PROVIDER_IDS="${ENABLED_PROVIDER_IDS:-lmstudio}"
export DEFAULT_PROVIDER_ID="${DEFAULT_PROVIDER_ID:-$SMOKE_MODEL_PROVIDER_ID}"
export DEFAULT_MODEL_NAME="${DEFAULT_MODEL_NAME:-$SMOKE_MODEL_NAME}"
export SMOKE_CHECK_RETRIES="${SMOKE_CHECK_RETRIES:-60}"
export SMOKE_CHECK_INTERVAL_SECONDS="${SMOKE_CHECK_INTERVAL_SECONDS:-2}"
export SMOKE_WAIT_TIMEOUT="${SMOKE_WAIT_TIMEOUT:-300}"

check_url() {
    local url="$1"
    local label="$2"
    local response_file error_file http_code curl_exit
    local last_http_code="" last_curl_exit="" last_error="" last_body=""

    response_file="$(mktemp)"
    error_file="$(mktemp)"
    trap 'rm -f "$response_file" "$error_file"' RETURN

    for _ in $(seq 1 "$SMOKE_CHECK_RETRIES"); do
        : >"$response_file"
        : >"$error_file"
        curl_exit=0
        http_code="$(curl --silent --show-error --location --output "$response_file" --write-out "%{http_code}" "$url" 2>"$error_file")" || curl_exit=$?

        if [ "$curl_exit" -eq 0 ] && [ "$http_code" -ge 200 ] && [ "$http_code" -lt 400 ]; then
            return 0
        fi

        last_http_code="$http_code"
        last_curl_exit="$curl_exit"
        last_error="$(<"$error_file")"
        last_body="$(<"$response_file")"
        last_body="${last_body//$'\n'/ }"
        last_body="${last_body:0:240}"
        sleep "$SMOKE_CHECK_INTERVAL_SECONDS"
    done

    echo "Smoke dependency unavailable: $label ($url)" >&2
    [ "$last_curl_exit" -ne 0 ] && echo "Last curl exit code: $last_curl_exit" >&2
    [ -n "$last_http_code" ]    && echo "Last HTTP status: $last_http_code" >&2
    [ -n "$last_error" ]        && echo "Last curl error: $last_error" >&2
    [ -n "$last_body" ]         && echo "Last response body: $last_body" >&2
    exit 1
}

case "$ACTION" in
    up)
        echo "Starting Docker stack with smoke-model defaults..."

        # Separate docker-compose flags (starting with -) from service names
        UP_FLAGS=()
        UP_SERVICES=()
        for arg in "$@"; do
            case "$arg" in
                -*) UP_FLAGS+=("$arg") ;;
                *)  UP_SERVICES+=("$arg") ;;
            esac
        done

        if [ "${#UP_SERVICES[@]}" -gt 0 ]; then
            docker compose --profile smoke up -d --wait --wait-timeout "$SMOKE_WAIT_TIMEOUT" "${UP_FLAGS[@]}" llama-cpp-smoke
            docker compose --profile smoke up -d --wait --wait-timeout "$SMOKE_WAIT_TIMEOUT" "${UP_FLAGS[@]}" "${UP_SERVICES[@]}"
        else
            docker compose --profile smoke up -d --wait --wait-timeout "$SMOKE_WAIT_TIMEOUT" "${UP_FLAGS[@]}"
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
    test)
        "$SMOKETEST_DIR/smoke.sh" check
        cd "$SMOKETEST_DIR"
        exec pnpm test -- "$@"
        ;;
    *)
        echo "Usage: $0 {up [service ...]|check|test [playwright args ...]}" >&2
        exit 1
        ;;
esac
