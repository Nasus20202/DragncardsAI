# Tasks

## 1. Establish what a persona has to fit into

- [x] 1.1 Read how a subagent is configured today: `_launch_child_agent`,
      `make_spawn_subagent_handler`, and `make_prompt_player_agent_handler` in
      `services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py`.
- [x] 1.2 Read the per-seat configuration that already solves half the problem —
      `runtime/player_agents.py` (`resolve_player_agent_config`, `fold_reasoning`),
      `repositories/players.py`, `api/routers/players.py`, `schemas/players.py` —
      and model a persona on it rather than inventing a parallel config system.
- [x] 1.3 Read the two existing global registries (`skill_registries`,
      `mcp_registries`) to settle scoping and key choice: deployment-global, keyed
      by name, `PUT` upserts.
- [x] 1.4 Read the migration runner (`schema_migrations/runner.py` and
      `dragncards_common.schema_migrations`) and the `0008` pair, so the new
      migration follows the same discovery and dialect-pair convention.
- [x] 1.5 Establish where a tool allowlist can be applied so it cannot widen:
      `prompt_run.py` computes `tool_definitions` → `mcp_tools` → `tool_mapping`,
      so filtering `tool_definitions` narrows both what the model sees and what
      can be dispatched.

## 2. Persona storage

- [x] 2.1 Add the `AgentPersona` model to `storage/models.py`: `name` primary
      key, `display_name`, `description`, `system_prompt`, `provider_id`,
      `model_name`, `gateway_options`, `provider_options`, `skills_json`,
      `allowed_tools_json`, `created_at`, `updated_at`, documenting that
      `skills_json`/`allowed_tools_json` of `NULL` mean "inherit" / "no
      narrowing".
- [x] 2.2 Add `default_subagent_persona` to `AgentSession`, nullable, documenting
      that it is the persona a spawn falls back to.
- [x] 2.3 Add `schema_migrations/sql/0009_agent_personas.postgresql.sql` and
      `0009_agent_personas.sqlite.sql`: create the table and add the session
      column, with the inherit/no-narrowing meaning recorded in a comment.
- [x] 2.4 Add `repositories/personas.py` — upsert, list, get, delete — and mix it
      into `Repository`. Deleting a persona clears it from any session that names
      it as a default, in the same transaction.
- [x] 2.5 Extend `delete_session` so it does not have to change: the persona
      column lives on `agent_sessions` and needs no separate sweep.

## 3. Persona resolution

- [x] 3.1 Add `runtime/personas.py`: `MAX_PERSONA_PROMPT_CHARS`,
      `PERSONA_NAME_PATTERN`, `ResolvedPersona`, `resolve_persona`,
      `persona_snapshot_from`, `session_persona_snapshot`, and the snapshot
      metadata key. `ResolvedPersona` exposes
      `provider_id`/`model_name`/`gateway_options`/`provider_options` so
      `_launch_child_agent` can consume it where it already consumes a resolved
      seat config.
- [x] 3.2 `resolve_persona` mirrors `resolve_player_agent_config`: unset
      provider/model inherit, options overlay, `skills_json` of `None` inherits
      the parent's enabled skills and a list (including empty) replaces them.
- [x] 3.3 Keep resolution pure so the inheritance and narrowing rules are
      directly testable without a database.

## 4. Persona API

- [x] 4.1 Add `schemas/personas.py`: request/response models with the length and
      count bounds on the fields themselves, and a `reasoning` block folded into
      `gateway_options` the way `PlayerConfigRequest` does.
- [x] 4.2 Add `api/routers/personas.py`: `GET /personas`, `GET /personas/{name}`,
      `PUT /personas/{name}`, `DELETE /personas/{name}`; validate the name slug,
      the provider against `ENABLED_PROVIDER_IDS`, and every named skill against
      the skill catalogue, naming the offending skill in the rejection. Register
      each named skill in `skill_registries` so a child session can enable it,
      the same way the players router does.
- [x] 4.3 Register the router in `runtime/app.py`.
- [x] 4.4 Accept and validate `default_subagent_persona` on session create and
      update, rejecting an unknown persona, and serialize it on session
      responses.

## 5. Starting a subagent from a persona

- [x] 5.1 `spawn_subagent` gains an optional `persona` argument; the tool
      description states it is optional, that omitting it inherits the caller's
      configuration, and that a persona changes prompt, skills, and tool access.
- [x] 5.2 Resolve the persona at spawn: explicit argument first, then the
      session's default, then none. An unknown persona returns an error result
      naming the request and the available personas, and creates nothing.
- [x] 5.3 Re-validate every skill the persona names against the skill catalogue
      before anything is created; a missing skill returns an error naming the
      persona and the skill, and creates nothing.
- [x] 5.4 Write the resolved persona snapshot into the child session's metadata
      and pass the resolved config and skills through the existing
      `_launch_child_agent` path, so the child's model config and skill rows are
      the persona's. Carry the persona name on `subagent_started` and on the tool
      result.
- [x] 5.5 Persona catalogue in the master system prompt: names and descriptions
      only, omitted entirely when no personas exist and never given to a
      subagent.
- [x] 5.6 Persona prompt in the subagent system prompt as its own `## Persona`
      section, appended to the parts list — concatenated as text, never used as a
      format string.
- [x] 5.7 Filter the child's `tool_definitions` by the snapshot's allowlist in
      `prompt_run`, before `as_openai_tools` and `as_mapping`, so an excluded tool
      is neither offered nor dispatchable. Built-in skill tools are outside the
      allowlist.

## 6. Dashboard

- [x] 6.1 Add the persona types to `features/shared/lib/types.ts` and the four
      persona endpoints to `features/play/lib/client-api.ts`.
- [x] 6.2 Add `features/personas/lib/personas.ts`: the editable draft, hydration
      from a stored persona, request assembly that omits unset fields so the
      server applies inheritance, and the prompt-length check.
- [x] 6.3 Add `features/personas/components/persona-editor.tsx` — list plus form,
      built from the shared field components, with an explicit empty state and
      surfaced errors — and `app/personas/page.tsx`.
- [x] 6.4 Add one nav entry for the page in
      `features/shell/components/app-shell.tsx`, changing nothing else about the
      shell.
- [x] 6.5 Add the default-persona picker to the Play settings panel and the
      session draft, rendering nothing when no personas exist.

## 7. Tests

- [x] 7.1 agent-orchestrator unit — persona CRUD through the API: create, read
      back, upsert over an existing name, list, delete, delete-again 404,
      read-unknown 404.
- [x] 7.2 agent-orchestrator unit — persona validation: bad name slug, oversized
      prompt, unsupported provider, unknown skill named on write (message names
      the skill), unknown session default.
- [x] 7.3 agent-orchestrator unit — resolution: unset provider/model inherit, set
      ones override, options overlay, unset skills inherit, empty skill list
      means none, reasoning folded into gateway options.
- [x] 7.4 agent-orchestrator unit — capture at start time: the child's model
      config, skill rows, and metadata snapshot come from the persona; editing the
      persona afterwards leaves the child's snapshot and rows unchanged; deleting
      the persona afterwards leaves them unchanged too.
- [x] 7.5 agent-orchestrator unit — narrow-never-widen: an allowlist removes the
      session's other tools; an allowlist naming a tool the catalogue does not
      have adds nothing; an excluded tool is absent from the dispatch mapping;
      no allowlist narrows nothing; `load_skill` survives narrowing.
- [x] 7.6 agent-orchestrator unit — a persona naming a missing skill fails the
      spawn with a message naming persona and skill and creates no child session
      or job; an unknown persona name does the same.
- [x] 7.7 agent-orchestrator unit — session default applies when no persona is
      named, an explicit name beats the default, no persona anywhere leaves the
      old inherit-everything behaviour intact, and deleting a persona clears it as
      a session default.
- [x] 7.8 agent-orchestrator unit — the persona prompt appears as its own section
      of a subagent prompt, the catalogue appears for a master job only when
      personas exist, and never for a subagent.
- [x] 7.9 agent-orchestrator unit — migration `0009` is discovered and applied by
      the existing runner test.
- [x] 7.10 dashboard unit — persona draft assembly and hydration, the
      prompt-length bound, the editor's list/create/edit/delete flow and empty
      state, and the picker's presence, persisted selection, clearing, and
      absence when no personas exist.

## 8. Keep the surrounding files current

- [x] 8.1 `services/agent-orchestrator/README.md` — an "Agent Personas" section
      covering the concept, the four endpoints, the request shape and field
      meanings, the bounds, capture-at-start-time, and the narrow-never-widen
      rule; plus the persona step in "Configure a new agent".
- [x] 8.2 `services/agent-orchestrator/AGENTS.md` — personas as a core concept,
      stating the capture rule and the narrowing invariant as instructions.
- [x] 8.3 Root `README.md` — personas named in the architecture summary and in
      what the dashboard covers.
- [x] 8.4 No new configuration key: the persona bounds are module constants in
      `runtime/personas.py`, matching `MAX_PLAYER_SKILLS` and the
      conversation-context bounds, neither of which is an environment variable.
      `.env.example` and `docker-compose.yaml` therefore need no entry, and the
      README says so explicitly so the next reader does not go looking.
- [x] 8.5 No change needed to the Swagger index or the dashboard proxy: both are
      generic over a service's OpenAPI document and carry no per-path list, so
      the persona endpoints appear automatically.

## 9. Checks

- [x] 9.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh` — clean.
- [x] 9.2 `./scripts/test.sh unit` — 1325 → 1410 passed, 0 failed.
      agent-orchestrator 309 → 359, dashboard 340 → 375, and game-service 378,
      history-service 100, eval-service 182, shared 16 unchanged.
- [x] 9.3 `openspec validate --all` — 16 passed, 1 failed: only the pre-existing
      `spec/typed-game-actions`. `change/dra-16-agent-personas` passes.
- [x] 9.4 Grepped this change directory for every placeholder marker the
      repository bans — the three-letter one, the four-letter one, a run of
      question marks, and the "to be" phrasings — and for empty sections under a
      heading. No hits: every section here is real prose.
- [ ] 9.5 Integration suite and Playwright verification: run by the orchestrator
      after merge. Five agents share this stack, so no Docker stack was started
      from this worktree.
