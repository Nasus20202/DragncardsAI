# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-learn-to-play`. The game primer
lives in [`SKILL.md`](SKILL.md) and its `references/` files; this preface does not alter
that shared game content. Harness details belong to `marvel-champions-play`'s selected
platform reference.

## The four services and MCP namespaces

| Service | Namespace | Role |
| --- | --- | --- |
| game-service | `game-service_*` | Neutral state and platform move surface |
| agent-orchestrator | `agent-orchestrator_*` | Sessions, prompts, jobs, findings |
| eval-service | `eval-service_*` | Move, round, and game evaluation |
| history-service | `history-service_*` | Events, snapshots, and restore |

Two platforms exist behind game-service: `dragncards` and `marvel-lcg`. A session is bound
to exactly one. The platform decides how state is read, how a move is expressed, and which
rules are enforced. The platform-build skills are `dragncards` and `marvel-lcg`; the play
skill owns live moves.

## Guardrails and workflow

Use **spawn, observe, decide, act, report**. This primer grants no tools and never
authorises a seat to act out of turn, use another seat's zone, advance a phase, or edit an
illegal-action finding. The coordinating agent and the selected platform harness own
those runtime decisions.
