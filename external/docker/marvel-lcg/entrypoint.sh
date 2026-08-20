#!/bin/sh

set -eu

if [ -z "${MARVEL_LCG_PASSWORD:-}" ]; then
    printf '%s\n' 'MARVEL_LCG_PASSWORD must be set before starting the marvel-lcg service.' >&2
    exit 1
fi

# The upstream engine reads configuration from launch.json/command-line
# variables, not from the environment. Generate the small runtime override in
# the container filesystem so the password is never committed or placed in the
# image layer, and keep all writable paths on Compose-managed volumes.
umask 077
runtime_config=/run/marvel-lcg/marvel-lcg-runtime.json
# ConfigVariables treats a leading slash as another command-line switch. This
# relative spelling resolves to the same tmpfs file from WORKDIR /app without
# putting the password-bearing config under the application source tree.
runtime_config_arg=../../run/marvel-lcg/marvel-lcg-runtime.json
mkdir -p "$(dirname "$runtime_config")"
python - <<'PY'
import json
import os

config = {
    "server_addresses": ["0.0.0.0:2345"],
    "password": os.environ["MARVEL_LCG_PASSWORD"],
    "image_servers": [
        "https://cerebrodatastorage.blob.core.windows.net/cerebro-cards/official/{card_id:U}.jpg",
        "https://marvelcdb.com/bundles/cards/{card_id}.png",
    ],
    "image_folders": ["/app/assets/pics"],
    "replay_folders": ["/app/replays"],
    "load_folders": ["/app/replays"],
    "game_statistics_file": "/app/runtime/statistics.json",
    "game_history_file": "/app/runtime/statistics.sqlite3",
    "campaign_progress_file": "/app/runtime/save_campaign_progress.json",
    "active_session_file": "/app/runtime/save_active_session.json",
    "quick_save_folder": "/app/runtime",
    "crash_file": "/app/runtime/crash.log",
    "editor": False,
    "statistics": True,
    "allow_custom_script": False,
}

with open("/run/marvel-lcg/marvel-lcg-runtime.json", "w", encoding="utf-8") as handle:
    json.dump(config, handle)
PY

exec python -u main.py -config_files "$runtime_config_arg"
