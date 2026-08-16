# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for the `dragncards` platform skill. The platform internals —
DragnLang, the plugin JSON, the engine architecture — live in
[`SKILL.md`](SKILL.md); this file says nothing about the platform. It says how the
platform knowledge relates to the DragncardsAI runtime.

## The four services

The DragnCards engine this skill documents is reached through a DragncardsAI deployment.
Four first-party services surround the table, each exposing its HTTP API and MCP surface
at `/mcp`:

| Service | What it is for |
| --- | --- |
| **game-service** | The live game. Holds the DragnCards session, exposes the simplified game state, and executes every game action — mulligan, deck-load, card moves, token changes, phase automation — as typed, validated tools. |
| **agent-orchestrator** | Sessions and jobs. Creates the session an agent runs in, submits prompts, streams job status and events, and attaches the MCP servers whose tools the agent calls. |
| **eval-service** | Grading. Turns recorded moves into per-player move/round/game evaluations through a judge, and communicates with that judge. |
| **history-service** | The recorded past. Stores the ordered event stream for every game, snapshots, and restore points. |

## MCP tool namespaces

Inside an agent session, tools carry the registry prefix of the MCP server that exposes
them. The namespaces an agent may see, by convention:

- `game-service_*` — state reads and typed game actions (`game-service_get_game_state`,
  `game-service_move_card`, the `game-service_*_marvel_champions` catalog tools, …).
- `agent-orchestrator_*` — session and job tools (`agent-orchestrator_get_job_status`,
  `agent-orchestrator_list_job_events`, `agent-orchestrator_report_illegal_action`, …).
- `eval-service_*` — evaluation tools (`eval-service_list_game_rounds`,
  `eval-service_create_evaluation`, `eval-service_get_evaluation`, …).
- `history-service_*` — recorded history tools (`history-service_list_recorded_games`,
  `history-service_list_game_events`, `history-service_list_game_timeline`, …).

## Strict guardrails

These hold for an agent that loads this skill:

1. **A seat must not act out of turn.** This is not a play skill; nothing here is
   permission to act on a table at any time, in turn or out (DRA-62/DRA-57).
2. **A seat must not use tools outside its allowed set.** DragnLang is not a way to act on
   a live table. A player agent has no `raw_action` and should not go looking for one —
   the typed game-service tools exist because an unvalidated action list corrupts the
   table for every seat. Reading this skill to understand *why* a tool behaves as it does
   is fine; hand-writing an action list against a game in progress is not (DRA-30).
3. **A seat must not advance the phase.** Phase automation belongs to the coordinating
   agent through the game-service tools, never to a seat through raw DragnLang (DRA-62).
4. **Illegal-action findings are not editable by the seat.** A finding recorded via
   `report_illegal_action` (DRA-30) is undone by the seat and resolved by the coordinating
   agent; platform knowledge does not change that.

## The workflow: spawn, observe, decide, act, report

Platform work follows the same workflow as everything else on the platform:

1. **Spawn** — load this skill when the task is building or debugging the platform: a
   plugin, a DragnLang action list, an automation rule, or an engine behaviour.
2. **Observe** — read the platform sources this skill points at (the engine evaluator, the
   plugin JSON, the channel code) and the game state through `game-service_get_game_state`
   when a live table is involved.
3. **Decide** — form the diagnosis or the plugin change from what the engine actually
   does, not from what an action summary claims.
4. **Act** — write plugin JSON or action lists *outside* a live game, and — if a live
   table must change — only through the typed game-service tools, never `raw_action`.
5. **Report** — state what the platform does, what you changed, and which files under
   `external/` it touched.

If you are playing a game, this is the wrong file: load `marvel-champions-play` to take a
hero's turn, `marvel-champions-orchestrator` to run a whole game, and
`marvel-champions-rules-reference` to settle a rules question.
