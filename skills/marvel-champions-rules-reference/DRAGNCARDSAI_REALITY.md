# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-rules-reference`. The rules corpus —
glossaries, keywords, timing, errata — lives in [`SKILL.md`](SKILL.md) and its resources
([`resources/golden-rules.md`](resources/golden-rules.md),
[`resources/round-structure.md`](resources/round-structure.md),
[`resources/glossary-A-D.md`](resources/glossary-A-D.md),
[`resources/glossary-E-O.md`](resources/glossary-E-O.md),
[`resources/glossary-P-Z.md`](resources/glossary-P-Z.md),
[`resources/keywords.md`](resources/keywords.md),
[`resources/timing.md`](resources/timing.md),
[`resources/deck-customization.md`](resources/deck-customization.md), and the rest of the
`resources/` directory); this file says nothing about the rules. It says what runtime you
answer questions in.

## The four services

You answer rules questions on a DragnCardsAI deployment. Four first-party services
surround the table, each exposing its HTTP API and MCP surface at `/mcp`:

| Service | What it is for |
| --- | --- |
| **game-service** | The live game. Holds the DragnCards session, exposes the simplified game state, and executes every game action — mulligan, deck-load, card moves, token changes, phase automation. |
| **agent-orchestrator** | Sessions and jobs. Creates the session you run in, submits prompts, streams job status and events, and attaches the MCP servers whose tools an agent calls. |
| **eval-service** | Grading. Turns recorded moves into per-player move/round/game evaluations through a judge, and communicates with that judge. |
| **history-service** | The recorded past. Stores the ordered event stream for every game, snapshots, and restore points. |

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

1. **A seat must not act out of turn.** Answers do not change whose turn it is; a rules
   answer is never permission to act for another seat or outside a turn (DRA-62/DRA-57).
2. **A seat must not use tools outside its allowed set.** This skill answers questions; it
   grants no tools and no table access. Which tools a seat holds is decided by the session
   and enforced by the seat guard (DRA-30).
3. **A seat must not advance the phase.** Nothing in the rules corpus authorises advancing
   the phase, the step marker, or the villain phase — those belong to the coordinating
   agent (DRA-62).
4. **Illegal-action findings are not editable by the seat.** A finding recorded via
   `report_illegal_action` (DRA-30) is undone by the seat and resolved by the coordinating
   agent; a rules answer does not close, delete, or edit one.

## The workflow: spawn, observe, decide, act, report

Answering a question follows the same shape as everything else an agent does on the
platform; `SKILL.md`'s lookup loop is the rules instantiation of it.

1. **Spawn** — a question arrives through the session that loaded this skill. Read the
   question in full before answering anything.
2. **Observe** — route the question through the lookup loop: name the terms, pick the
   smallest set of references that can settle it, and load only those. If the question is
   about the harness rather than the rules, route to `marvel-champions-play` instead.
3. **Decide** — compose the answer from the loaded references, applying errata to any
   named card first and citing the rule or glossary entry each claim came from.
4. **Act** — deliver the answer with its citations, and stop. Do not volunteer adjacent
   rulings; a rules answer never mutates the board, so there is no game action to take.
5. **Report** — when the question cannot be answered from the references, say so plainly
   and say what you checked, rather than composing an answer from recollection.

An answer that cannot be cited is worse than no answer: the judge and the orchestrator
both rely on this corpus being the authority.
