# Rebuild coupled DragnCards assets before starting infrastructure

## User report

> "Implementation lane DRA-71. Worktree: /home/nasus/Dev/DragncardsAI-worktrees/wt-dra71. Create full OpenSpec change `dra-71-fix-board-layout`, then address the reported DragnCards scattered/overlapping board. Scope: Docker build/start scripts, compose configs, docs, test scripts, and only rendering code if a clean version-matched rebuild fails to fix it. First prove image/plugin artifact mismatch from current local Docker state; use the smallest reliable fix that ensures normal infrastructure workflow rebuilds/recreates coupled frontend/backend/plugin assets after checked-out submodule changes, without wiping user game data by default. Add regression diagnostics/tests, run them, archive OpenSpec, commit. Do not touch history or Marvel game-service code. Return root cause, exact commands, commits, validation, and any remaining manual browser verification."

## Why

The local stack was serving external assets built from an older checkout. The
checked-out DragnCards and plugin commits were `45b3a76dd6c5b979e410386f7768470b448eb913`
(2026-08-23) and `d435859dc59ea130fc5a5ccfad7c3098db9e0882` (2026-08-22), while
the frontend, backend, and plugin images were created on 2026-08-05. The running
plugin image and volume contained `json/actionLists.json` with SHA-256
`f8e456d24b0af51f86877d9367eb5e4692899f02dead592124c65f5735f768a3`; the
checked-out source was `1236551facb504f6543294e244e788250793dd598f966fee2aead189f7397245`.
The backend mounted that stale volume, which also contained nested `json/json`
and `tsv/tsv` directories from the old copy command. The three assets were not a
version-matched release unit. This change fixes lifecycle synchronization first;
rendering source remains out of scope unless a clean rebuild still fails.

## What changes

- Rebuild the coupled DragnCards frontend, backend, and plugin image from checked-out
  submodule source during normal local application and infrastructure starts.
- Force-recreate the coupled services so a changed plugin image also restarts the
  backend that mounts its generated artifacts and refreshes the frontend container.
- Replace only the plugin artifact directories in the named artifact volume before
  copying the image contents, preventing stale root files and nested copies.
- Keep game and engine state volumes intact; no normal start or restart performs a
  volume removal or `down -v` operation.
- Add a Compose/lifecycle regression check and a live manifest comparison whenever
  a DragnCards stack is available.
- Document the repair behavior and the explicit infrastructure regression command.

## Capabilities

### Modified capabilities

- `infrastructure` — normal local startup keeps the coupled DragnCards assets in
  sync and preserves persistent game data.

## Non-goals

- No DragnCards frontend rendering changes.
- No history-service changes.
- No Marvel game-service changes.
- No deletion of user game, replay, engine, database, or observability volumes by
  the normal lifecycle commands.
