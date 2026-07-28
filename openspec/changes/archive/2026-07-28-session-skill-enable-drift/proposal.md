# Let sessions enable any on-disk skill and tolerate stale skill state

## Why

A user reported "skill not enabled for session -> I cannot play". Saving a
session's configuration in the Play workspace failed with
`Skill not enabled for session`, and because the dashboard aborts a save on the
first failed request, no other setting was applied either — the session could
not be configured, so it could not play.

Reproduced against the running stack. A `session_enabled_skills` row is a soft
toggle: disabling a skill flips `enabled` to false instead of deleting the row.
Almost nothing honoured that flag, and the parts that did disagreed with the
parts that did not:

1. **The session payload reported disabled skills as assigned.**
   `serialize_session_summary` listed every `enabled_skills` row regardless of
   the flag, while `GET /sessions/{id}/skills` filtered on it. The dashboard
   builds its skill toggles from the session payload, so a skill the user had
   just switched off came back switched on.
2. **Disabling was not idempotent.** `DELETE /sessions/{id}/skills/{name}`
   returned 404 `Skill not enabled for session` when the row was missing *or*
   already disabled. The dashboard saves a config by replaying the desired skill
   set, so the toggle desync in (1) made it replay a disable for an
   already-disabled skill — the exact 404 the user hit, aborting the save.
3. **Enabling depended on a lazily-built registry.** Enabling a skill needs a
   `skill_registries` row (the session/skill join is a foreign key), but rows
   only ever appeared as a side effect of `POST /sessions/{id}/skills`. Nothing
   synced the skill roots into the table, so it held a partial, stale view of
   what is on disk — the deployed database had 3 rows for 5 on-disk skills — and
   `PATCH /sessions/{id}/skills/{name}` returned 404
   `Session or skill not found` for any skill that had not been through that one
   route.
4. **"Disabled" did not reach the agent.** The system prompt, the built-in
   skill-loading tools, and the session tool preview were all built from the
   unfiltered assignment list, so a disabled skill was still advertised to the
   model and still loadable.

## What Changes

- **agent-orchestrator (startup)** — sync the on-disk skills into
  `skill_registries` at boot, upsert-only, so the table reflects the skill roots
  instead of whichever skills happened to be enabled once. Rows for skills no
  longer on disk are kept so existing session assignments keep their foreign key.
- **agent-orchestrator (enablement)** — every route that enables a skill for a
  session registers it from the skill roots first, so any skill present on disk
  is enablable, including one added after boot. A skill that is not on disk is
  still rejected with 400 `Unknown skill`.
- **agent-orchestrator (disablement)** — disabling is idempotent: a skill that is
  already off, was never enabled, or does not exist returns success, because the
  session is already in the requested state. An unknown session is still 404.
- **agent-orchestrator (serialization)** — the session summary and detail
  payloads list only skills that are actually enabled, matching
  `GET /sessions/{id}/skills`.
- **agent-orchestrator (runtime)** — one shared `enabled_skill_assignments`
  helper filters assignments, used by the system prompt, the built-in tool
  registry, the session tool preview, the context-metadata estimate, and
  subagent/player-agent skill inheritance, so switching a skill off actually
  withdraws it from the agent.
- **agent-orchestrator (cleanup)** — remove the unreachable
  `GET /skills` handler in the sessions router. The catalog router is mounted
  first and already owns that path, so the sessions variant never served a
  request; it only made the skill registry look like the dashboard's source of
  available skills.

## Non-goals

- No dashboard change. The dashboard's save loop is correct once the API stops
  reporting disabled skills as assigned and stops rejecting no-op disables.
  Making that loop resilient to per-request failures in general is separate.
- The `enabled` flag stays a soft toggle; rows are not hard-deleted on disable.
- Pruning `skill_registries` rows for skills removed from disk is out of scope —
  it would break the foreign key from existing session assignments.
