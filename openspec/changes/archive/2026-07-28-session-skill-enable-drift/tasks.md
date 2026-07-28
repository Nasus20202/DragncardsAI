# Tasks

## 1. Reproduce

- [x] 1.1 Drive the running stack and confirm `DELETE /sessions/{id}/skills/{name}`
      returns 404 `Skill not enabled for session` both for a never-enabled skill
      and for one already disabled.
- [x] 1.2 Confirm the session payload still lists a skill after it is disabled,
      which is what makes the dashboard replay that disable.
- [x] 1.3 Confirm `skill_registries` holds fewer skills than the skill roots and
      that `PATCH /sessions/{id}/skills/{name}` 404s for an unregistered one.

## 2. Skill registry

- [x] 2.1 Add `_sync_skill_registry` and call it from the app lifespan so the
      on-disk skills are upserted into `skill_registries` at boot.
- [x] 2.2 Add a router helper that registers an on-disk skill before enabling it,
      and use it from `POST /skills`, `POST /sessions/{id}/skills`, and
      `PATCH /sessions/{id}/skills/{name}`.
- [x] 2.3 Remove the unreachable `GET /skills` handler from the sessions router.

## 3. Drift-tolerant enablement

- [x] 3.1 Make `DELETE /sessions/{id}/skills/{name}` a no-op when the skill is
      already off or was never enabled; keep 404 for an unknown session.
- [x] 3.2 Make `PATCH ... {"enabled": false}` tolerate the same states.
- [x] 3.3 Filter disabled assignments out of the session summary and detail
      payloads.

## 4. Honour the flag in the runtime

- [x] 4.1 Add `enabled_skill_assignments` to `runtime/skills.py`.
- [x] 4.2 Use it for the system prompt and built-in tool registry in
      `prompt_run`, the session tool preview in `api/tool_catalog`, the
      context-metadata estimate in `session_transcript`, and subagent and
      player-agent skill inheritance.

## 5. Tests

- [x] 5.1 Add `tests/unit/test_app_session_skills.py` covering: enabling an
      on-disk skill with no prior registration, rejecting a skill absent from
      disk, a disabled skill absent from the session payload, idempotent
      disable, disable of a never-enabled skill, unknown-session 404,
      re-enabling a disabled skill, the startup sync, a skill added after boot,
      the filter helper, and a disabled skill absent from the system prompt.
- [x] 5.2 Update the two tests that asserted the old behaviour: the repeat
      delete in `test_app_sessions.py` and the pre-registration probe in
      `test_app_player_configs.py`.
- [x] 5.3 Update `tests/integration/test_api_skills.py` so a repeat delete
      expects 204.

## 6. Verification

- [x] 6.1 `./scripts/lint.sh --fix` clean.
- [x] 6.2 `./scripts/test.sh unit` passes for every service.
- [x] 6.3 `./scripts/test.sh integration agent-orchestrator` passes.
- [x] 6.4 Replay the dashboard's save sequence end-to-end against the fixed
      service and confirm every step succeeds.
- [x] 6.5 Sync `openspec/specs/agent-orchestrator/spec.md`.
