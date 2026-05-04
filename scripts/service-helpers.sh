#!/bin/bash

list_services() {
    printf '%s\n' \
        "game-service"
}


resolve_services() {
    local root_dir="$1"
    shift

    if [ "$#" -gt 0 ]; then
        printf '%s\n' "$@"
        return
    fi

    list_services
}


service_dir() {
    local root_dir="$1"
    local service="$2"

    printf '%s/services/%s\n' "$root_dir" "$service"
}


service_env_file() {
    local root_dir="$1"
    local service="$2"

    printf '%s/.env\n' "$(service_dir "$root_dir" "$service")"
}


service_uv_env_args() {
    local root_dir="$1"
    local service="$2"
    local env_file

    env_file="$(service_env_file "$root_dir" "$service")"
    if [ -f "$env_file" ]; then
        printf ' --env-file "%s"' "$env_file"
    fi
}


service_test_command() {
    local root_dir="$1"
    local service="$2"
    local mode="$3"
    local env_args

    env_args="$(service_uv_env_args "$root_dir" "$service")"

    case "$service" in
        game-service)
            case "$mode" in
                unit)
                    printf 'cd "%s/services/game-service" && exec uv run pytest tests/unit/ -n auto -n auto -v' "$root_dir"
                    ;;
                integration)
                    printf 'cd "%s/services/game-service" && exec uv run%s pytest tests/integration/ -n auto -v' "$root_dir" "$env_args"
                    ;;
                all)
                    printf 'cd "%s/services/game-service" && exec uv run%s pytest tests/ -n auto -v' "$root_dir" "$env_args"
                    ;;
                *)
                    return 1
                    ;;
            esac
            ;;
        *)
            return 1
            ;;
    esac
}


validate_service() {
    local root_dir="$1"
    local service="$2"
    local dir
    local known="no"

    while IFS= read -r candidate; do
        if [ "$candidate" = "$service" ]; then
            known="yes"
            break
        fi
    done < <(list_services)

    if [ "$known" != "yes" ]; then
        echo "Unknown service: $service" >&2
        exit 1
    fi

    dir="$(service_dir "$root_dir" "$service")"
    if [ ! -d "$dir" ]; then
        echo "Service directory not found: $dir" >&2
        exit 1
    fi
}


service_start_command() {
    local root_dir="$1"
    local service="$2"
    local env_args

    env_args="$(service_uv_env_args "$root_dir" "$service")"

    case "$service" in
        game-service)
            printf 'cd "%s/services/game-service" && exec uv run%s game-service' "$root_dir" "$env_args"
            ;;
        *)
            return 1
            ;;
    esac
}


service_http_port() {
    local service="$1"

    case "$service" in
        game-service)
            printf '%s' '8000'
            ;;
        *)
            return 1
            ;;
    esac
}
