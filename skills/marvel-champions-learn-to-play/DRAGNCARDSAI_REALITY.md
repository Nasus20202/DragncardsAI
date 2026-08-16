# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-learn-to-play`. The primer itself —
the shape of a round, what a player may do on a turn, the five villain-phase steps — lives
in [`SKILL.md`](SKILL.md) and its references
([`references/quick-reference.md`](references/quick-reference.md),
[`references/player-turn.md`](references/player-turn.md),
[`references/villain-phase.md`](references/villain-phase.md),
[`references/setup.md`](references/setup.md),
[`references/encounter.md`](references/encounter.md),
[`references/status.md`](references/status.md),
[`references/card-types.md`](references/card-types.md),
[`references/deck-customization.md`](references/deck-customization.md),
[`references/schemes-status-and-damage.md`](references/schemes-status-and-damage.md));
this file says nothing about the game. It says what runtime the game is played in.

## The four services

The game this primer describes is played on a DragnCardsAI deployment. Four first-party
services surround the table, each exposing its HTTP API and MCP surface at `/mcp`:

| Service | What it is for |
| --- | --- |
| **game-service** | The live game. Holds the DragnCards session, exposes the simplified game state, and executes every game action — mulligan, deck-load, card moves, token changes, phase automation. |
| **agent-orchestrator** | Sessions and jobs. Creates the session an agent runs in, submits prompts, streams job status and events, and attaches the MCP servers whose tools the agent calls. |
| **eval-service** | Grading. Turns recorded moves into per-player move/round/game evaluations through a judge, and communicates with that judge. |
| **history-service** | The recorded past. Stores the ordered event stream for every game, snapshots, and restore points — what the evaluator grades. |

## MCP tool namespaces

Inside an agent session, tools carry the registry prefix of the MCP server that exposes
them. The namespaces an agent may see, by convention:

- `game-service_*` — state reads and game actions (`game-service_get_game_state`,
  `game-service_move_card`, the `game-service_*_marvel_champions` catalog tools, …).
- `agent-orchestrator_*` — session and job tools (`agent-orchestrator_get_job_status`,
  `agent-orchestrator_list_job_events`, `agent-orchestrator_report_illegal_action`, …).
- `eval-service_*` — evaluation tools (`eval-service_list_game_rounds`,
  `eval-service_create_evaluation`, `eval-service_get_evaluation`, …).
- `history-service_*` — recorded history tools (`history-service_list_recorded_games`,
  `history-service_list_game_events`, `history-service_list_game_timeline`, …).

## Strict guardrails

These hold for an agent that loads this skill:

1. **A seat must not act out of turn.** The primer describes turns; it does not authorise
   acting outside one. A seat acts only when it is its turn (DRA-62/DRA-57).
2. **A seat must not use tools outside its allowed set.** This primer grants no tools; a
   seat's tool set comes from its session and is enforced by the seat guard (DRA-30).
3. **A seat must not advance the phase.** Phase transitions and the villain phase belong
   to the coordinating agent, never to a seat (DRA-62).
4. **Illegal-action findings are not editable by the seat.** A finding recorded via
   `report_illegal_action` (DRA-30) is undone by the seat and resolved by the coordinating
   agent; nothing in this primer changes that.

## The workflow: spawn, observe, decide, act, report

The primer supports agents through the same workflow everything else on the platform
follows:

1. **Spawn** — load this skill when you need the shape of a round quickly, or the
   vocabulary before the rules reference makes sense.
2. **Observe** — read the primer and route: how to execute a play against a live table is
   `marvel-champions-play` (which tool, which group id, which argument); the authority for
   a keyword, timing window, or card interaction is `marvel-champions-rules-reference`.
   Where they differ, this skill is the one that is wrong.
3. **Decide** — use the summary to frame a question or a plan, then move to the skill that
   owns the detail before acting.
4. **Act** — the primer itself takes no game action. Execution happens through
   `marvel-champions-play`'s game-service recipes on the live table.
5. **Report** — when the primer cannot settle a question, name the skill that can, or say
   the question is out of its scope.

The primer is a summary that trades precision for speed; it is never the authority.
