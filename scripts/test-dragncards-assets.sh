#!/bin/bash
# Validate the DragnCards image/plugin coupling and, when the stack is running,
# compare the mounted plugin volume with the plugin image artifacts.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 - <<'PY'
import json
import subprocess
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


compose = json.loads(
    subprocess.check_output(
        ["docker", "compose", "config", "--format", "json"], text=True
    )
)
services = compose["services"]
required = {
    "dragncards-mc-plugin",
    "dragncards-backend",
    "dragncards-frontend",
}
if not required.issubset(services):
    fail(f"missing coupled services: {sorted(required - services.keys())}")

plugin = services["dragncards-mc-plugin"]
entrypoint = " ".join(plugin["entrypoint"])
for fragment in (
    "rm -rf /output/json /output/tsv",
    "cp -r /plugin/json/. /output/json/",
    "cp -r /plugin/tsv/. /output/tsv/",
):
    if fragment not in entrypoint:
        fail(f"plugin entrypoint does not contain {fragment!r}")

plugin_volume = next(
    volume
    for volume in plugin["volumes"]
    if volume["target"] == "/output"
)
backend_volume = next(
    volume
    for volume in services["dragncards-backend"]["volumes"]
    if volume["target"] == "/plugin"
)
if plugin_volume["source"] != backend_volume["source"]:
    fail("backend and plugin do not share the generated artifact volume")

expected_builds = {
    "dragncards-mc-plugin": "external/docker/mc-plugin/Dockerfile",
    "dragncards-backend": "external/docker/backend/Dockerfile",
    "dragncards-frontend": "external/docker/frontend/Dockerfile",
}
root = str(Path.cwd())
for service, dockerfile in expected_builds.items():
    build = services[service]["build"]
    if build["context"] != root or build["dockerfile"] != dockerfile:
        fail(f"{service} build is not rooted at the checked-out source")

helper = Path("scripts/docker-infrastructure.sh").read_text()
for fragment in (
    'build "${COUPLED_DRAGNCARDS_SERVICES[@]}"',
    "--force-recreate",
    '"${COUPLED_DRAGNCARDS_SERVICES[@]}"',
):
    if fragment not in helper:
        fail(f"infrastructure helper is missing {fragment!r}")

print("PASS: Compose and lifecycle coupling replace stale plugin assets safely")
PY

# A running stack gives this regression check a second, runtime assertion. The
# lookup is label-based so it also works when a worktree uses a different Compose
# project name than the currently running local stack.
backend_container="$(docker ps -aq --filter 'label=com.docker.compose.service=dragncards-backend' | python3 -c 'import sys; print(next((line.strip() for line in sys.stdin if line.strip()), ""))')"
if [ -z "$backend_container" ]; then
    echo "SKIP: no running DragnCards backend container for live artifact comparison"
    exit 0
fi

plugin_container="$(docker ps -aq --filter 'label=com.docker.compose.service=dragncards-mc-plugin' | python3 -c 'import sys; print(next((line.strip() for line in sys.stdin if line.strip()), ""))')"
if [ -z "$plugin_container" ]; then
    echo "SKIP: no plugin container for live artifact comparison"
    exit 0
fi

plugin_volume="$(docker inspect "$backend_container" --format '{{range .Mounts}}{{if eq .Destination "/plugin"}}{{.Name}}{{end}}{{end}}')"
plugin_image="$(docker inspect "$plugin_container" --format '{{.Config.Image}}')"
if [ -z "$plugin_volume" ]; then
    echo "SKIP: running backend has no /plugin artifact volume"
    exit 0
fi

manifest() {
    local location="$1"
    docker run --rm -v "$plugin_volume:/output:ro" "$plugin_image" sh -c \
        "find $location -type f -exec sha256sum {} \\; | sed 's#  $location/#  #' | sort"
}

image_manifest="$(docker run --rm "$plugin_image" sh -c \
    "find /plugin -type f -exec sha256sum {} \\; | sed 's#  /plugin/#  #' | sort")"
volume_manifest="$(manifest /output)"
if [ "$image_manifest" != "$volume_manifest" ]; then
    echo "FAIL: mounted plugin artifacts do not match the plugin image" >&2
    diff -u <(printf '%s\n' "$image_manifest") <(printf '%s\n' "$volume_manifest") || true
    exit 1
fi

echo "PASS: mounted plugin artifacts match $plugin_image"
