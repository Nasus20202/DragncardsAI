# Tasks

## 1. Orchestrator skill

- [x] 1.1 Add `skills/marvel-champions-orchestrator/SKILL.md` with frontmatter
      (`name`, `description`, `metadata`) and the end-to-end procedure: roster
      check, game setup, the round loop, win/loss detection, and round logging.
- [x] 1.2 Add `skills/marvel-champions-orchestrator/references/round-loop.md`
      mapping each of the ten round steps onto game-service MCP tools.
- [x] 1.3 Add `skills/marvel-champions-orchestrator/references/player-turn-prompt.md`
      defining the prompt contract for a seat's turn and the boundaries a player
      agent must not cross.

## 2. agent-orchestrator — storage

- [x] 2.1 Add the `SessionPlayerConfig` model (`session_player_configs`) with a
      composite `session_id` + `player_id` primary key, cascade delete from
      `agent_sessions`, and a `player_configs` relationship on `AgentSession`.
- [x] 2.2 Add migration `0008_session_player_configs` for both PostgreSQL and
      SQLite.
- [x] 2.3 Add `PlayerConfigRepositoryMixin` (`repositories/players.py`) with
      upsert, list, get, and delete, and compose it into `Repository`.
- [x] 2.4 Eager-load `player_configs` in `RepositoryBase._session_query()` and
      `_job_query()` so the runtime sees the roster without an extra query.

## 3. agent-orchestrator — API

- [x] 3.1 Add `schemas/players.py`: `PlayerReasoningConfig`,
      `PlayerConfigRequest`, `PlayerConfigResponse`, `PlayerConfigListResponse`,
      with seat-id, skill-count, and display-name bounds.
- [x] 3.2 Add `api/routers/players.py` with `GET/PUT/DELETE
      /sessions/{id}/players[/{player_id}]`, validating seat id, provider
      enablement, session existence, and skill resolvability.
- [x] 3.3 Serialize player configs on `SessionSummary`/`SessionDetail` and
      register the router in `runtime/app.py`.

## 4. agent-orchestrator — runtime

- [x] 4.1 Add `runtime/player_agents.py`: seat-id validation, reasoning folding,
      and the pure `resolve_player_agent_config(parent_session, config)`.
- [x] 4.2 Extract the shared child-spawn core out of
      `make_spawn_subagent_handler` so a child can be created with an explicit
      model config, skill list, name, and metadata.
- [x] 4.3 Add the `list_player_agents` and `prompt_player_agent` handlers and
      register them on master jobs only when the session has a roster; thread
      the roster through `build_builtin_registry`, `prompt_run.py`, and
      `api/tool_catalog.py`.
- [x] 4.4 Seed the child session's metadata with `player_id` and the
      orchestrator's `game_id`.

## 5. Player identity on the timeline

- [x] 5.1 Add an optional `player` field to the agent-move envelope payload in
      `history_emitter.py`.
- [x] 5.2 Read `metadata.player_id` in
      `PromptRunService._emit_agent_move_event` and pass it through.
- [x] 5.3 eval-service: prefer an explicit `payload.player` in
      `attribute_move`, ahead of the single-player short-circuit and the
      `firstPlayer` rotation.

## 6. Dashboard plumbing

- [x] 6.1 Add `PlayerAgentConfig` / `PlayerAgentDraft` types and a
      `player-agents.ts` lib with default-draft creation and draft assembly that
      omits unset fields so the server applies inheritance.
- [x] 6.2 Add `listPlayerAgents` / `setPlayerAgent` / `deletePlayerAgent` to the
      Play client API.

## 7. Tests

- [x] 7.1 agent-orchestrator: player-config API tests — CRUD, inheritance echo,
      and each validation failure.
- [x] 7.2 agent-orchestrator: `resolve_player_agent_config` unit tests —
      inheritance, override, option overlay, reasoning fold and disable, skills
      override and inherit.
- [x] 7.3 agent-orchestrator: builtin-tool tests — registration gated on the
      roster, `list_player_agents` output, `prompt_player_agent` creating a
      correctly configured and tagged child, and its error paths.
- [x] 7.4 agent-orchestrator: history emitter carries `player` only when the
      session represents a seat.
- [x] 7.5 eval-service: explicit `payload.player` wins over inference, works
      without derivable state, and legacy events are unaffected.
- [x] 7.6 dashboard: `player-agents.ts` draft assembly tests.

## 8. Verification and specs

- [x] 8.1 `./scripts/lint.sh --fix` clean.
- [x] 8.2 `./scripts/test.sh unit` green.
- [x] 8.3 Sync `openspec/specs/` — new `game-orchestration` capability, updated
      `agent-orchestrator`, `llm-capabilities`, and `agent-move-evaluation`.
