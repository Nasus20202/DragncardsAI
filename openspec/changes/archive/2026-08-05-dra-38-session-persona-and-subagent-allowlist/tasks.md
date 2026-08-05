# Tasks

Ordered so the enforcement point exists before anything offers the control it
enforces. Sections 1–4 are the orchestrator, 5 is the dashboard, 6 is verification.

## 1. Confirm the existing shapes before changing them

- [x] 1.1 Confirm `session_enabled_skills` is the per-session selection from a
      deployment-global registry, with a soft `enabled` toggle read through
      `enabled_skill_assignments`, and that this is the shape the issue means by
      "like for skills".
- [x] 1.2 Confirm `_resolve_spawn_persona` is the single point every spawn's
      persona resolution passes through, including the fall-through to
      `default_subagent_persona`.
- [x] 1.3 Confirm `session_persona_snapshot` / `persona_prompt_from_snapshot` /
      `narrow_tool_definitions` are read from session metadata at job start and
      would apply to a top-level job unchanged if the snapshot were present.
- [x] 1.4 Confirm `build_system_prompt` takes the whole persona catalogue and has
      no persona-prompt parameter, so a top-level job cannot currently carry one.
- [x] 1.5 Confirm the highest existing migration is `0012`, so `0013` is free.
- [x] 1.6 Confirm `PATCH /sessions` accepts a client-supplied `metadata` body, so
      putting a snapshot there needs the key to be server-owned.

## 2. Storage

- [x] 2.1 Add migration `0013_session_persona_and_subagent_allowlist` in both
      dialects: `agent_sessions.session_persona`, the `session_allowed_subagents`
      table, and the backfill of existing sessions from the persona catalogue.
- [x] 2.2 Add `AgentSession.session_persona` and the `SessionAllowedSubagent`
      model with its `allowed_subagents` relationship.
- [x] 2.3 Eager-load `allowed_subagents` (and its persona) in `_session_query` and
      `_job_query`, so the spawn guard needs no extra round trip.
- [x] 2.4 Accept `session_persona` in `create_session` and `update_session`.
- [x] 2.5 Add `set_subagent_allowed`, `list_session_allowed_subagents`,
      `remove_subagent_allowance`, and the atomic
      `replace_session_allowed_subagents`.
- [x] 2.6 Sweep allowlist rows in `delete_session`, and in `delete_persona` clear
      the session persona name and delete every allowance naming the persona.

## 3. Runtime

- [x] 3.1 Add `session_persona_snapshot_for`, recording only the fields a session
      applies.
- [x] 3.2 Add `allowed_subagent_names` and `allowed_subagent_personas`, both
      reading the soft `enabled` flag.
- [x] 3.3 Add `subagent_refusal_message`, with a distinct empty-allowlist wording.
- [x] 3.4 Enforce the allowlist in `_resolve_spawn_persona`, above the persona
      lookup, covering the named persona and the session default alike.
- [x] 3.5 Give `build_system_prompt` a `persona_prompt` parameter and filter its
      persona catalogue to the session's allowlist.
- [x] 3.6 Pass the session's own persona prompt and its allowed personas from
      `prompt_run`'s non-subagent branch.
- [x] 3.7 Update `spawn_subagent`'s tool description to state that the listed
      personas are the only permitted names and that none listed means none
      permitted.

## 4. API

- [x] 4.1 Add `session_persona` and `allowed_subagents` to the session create and
      update requests and to the session responses, each carrying the rule in its
      OpenAPI description.
- [x] 4.2 Write the persona snapshot on create and update, and merge the stored
      snapshot back over a client-supplied `metadata` body so it can be neither
      forged nor dropped.
- [x] 4.3 Validate `default_subagent_persona` against the allowlist the request
      produces, before either is written, on both create and update.
- [x] 4.4 Refuse revoking a persona that is still the session's default, on the
      per-persona `PATCH` and `DELETE`.
- [x] 4.5 Add `allow_session_subagent`, `list_session_subagents`,
      `set_session_subagent_allowed` and `disallow_session_subagent`, with the
      list reporting every persona and an `allowed` flag.
- [x] 4.6 Serialize `session_persona` and the sorted allowlist on session
      summaries and details.

## 5. Dashboard

- [x] 5.1 Add `session_persona`, `allowed_subagents` and
      `SubagentAllowanceResponse` to the shared types, and `sessionPersona` /
      `allowedSubagents` to `SessionDraft`.
- [x] 5.2 Carry both through `createDefaultDraft`, `createNewSessionDraft`,
      `buildDraftFromSession` and the last-used-draft parser, treating an absent
      allowlist as empty.
- [x] 5.3 Send both on create and on save, in the same request as
      `default_subagent_persona`.
- [x] 5.4 Give `PersonaPicker` optional label/id/test-id props and a `restrictTo`
      narrowing, without changing its existing call site's behaviour.
- [x] 5.5 Add the `SubagentAllowlist` component, built from the existing toggle
      row, always stating in words which state the allowlist is in.
- [x] 5.6 Wire the session persona picker, the allowlist, and the narrowed default
      picker into the settings panel, clearing the default when the persona it
      names is revoked.

## 6. Tests and documentation

- [x] 6.1 Unit: a persona off the allowlist is refused, an empty allowlist permits
      none, a disallowed session default is refused, and a switched-off allowance
      stops permitting — each failing without the dispatch check.
- [x] 6.2 Unit: the session persona reaches the session's own system prompt,
      narrows its tools, and leaves its provider and model alone.
- [x] 6.3 Unit: the catalogue in the system prompt lists the allowlist only, and
      is absent entirely when the allowlist is empty.
- [x] 6.4 Unit (API): the persona snapshot is captured on assignment, survives an
      edit to the persona, cannot be forged or dropped through `metadata`, and
      outlives the persona's deletion while the name is cleared.
- [x] 6.5 Unit (API): the allowlist endpoints add, toggle, list with flags and
      remove; a default outside the allowlist is refused on create and update; and
      revoking the default persona is refused unless cleared in the same request.
- [x] 6.6 Integration: a disallowed persona named on a spawn driven entirely over
      HTTP creates no child, and the same call with the persona allowed does.
- [x] 6.7 Dashboard: the allowlist states its empty and non-empty cases, adds a
      persona, and clears the default when revoking it; the default picker offers
      only allowed personas; the session persona picker is not narrowed by it.
- [x] 6.8 Update the agent-orchestrator README's session and persona sections and
      `services/agent-orchestrator/AGENTS.md`'s persona concept.
- [x] 6.9 Run `./scripts/lint.sh --fix`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration agent-orchestrator`, and the dashboard's
      `pnpm typecheck`.
- [x] 6.10 Drive the settings panel in a browser: set a session persona, tick and
      untick an allowed subagent, reload, and confirm both persisted.
