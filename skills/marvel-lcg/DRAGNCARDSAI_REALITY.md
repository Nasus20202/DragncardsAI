# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-lcg`, the platform-build skill. Platform
internals live in [`SKILL.md`](SKILL.md). Playing a hand belongs to
[`marvel-champions-play`](../marvel-champions-play/SKILL.md) and its
[`marvel-lcg.md`](../marvel-champions-play/references/marvel-lcg.md) harness reference;
Marvel Champions rules remain in the shared rules skills.

## The four services

| Service | What it is for |
| --- | --- |
| **game-service** | Platform-neutral state and the platform's move surface |
| **agent-orchestrator** | Sessions, prompts, jobs, and seat guardrails |
| **eval-service** | Move, round, and game evaluation |
| **history-service** | Ordered events, snapshots, and restore |

## MCP namespaces

- `game-service_*` — neutral state and marvel-lcg option tools
- `agent-orchestrator_*` — sessions, prompts, jobs, and findings
- `eval-service_*` — evaluation requests and verdicts
- `history-service_*` — recorded games, timelines, events, and snapshots

Two platforms exist behind `game-service`: `dragncards` and `marvel-lcg`. A session is
bound to exactly one. The platform decides how state is read, how a move is expressed,
and which rules of play are enforced. The corresponding platform-build skills are
`dragncards` and `marvel-lcg`; the play and orchestrator skills own live play.

## Guardrails and workflow

The workflow is **spawn, observe, decide, act, report**. A seat acts only while its
platform is asking it, uses only its platform's option surface, and never edits an
illegal-action finding via `report_illegal_action`. The orchestrator verifies state and
resolves findings; a platform acknowledgement is not proof that a choice advanced.
