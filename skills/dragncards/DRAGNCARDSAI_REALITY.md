# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for the `dragncards` platform-build skill. Platform
internals live in [`SKILL.md`](SKILL.md); this file is not a play contract. Playing a
hand belongs to [`marvel-champions-play`](../marvel-champions-play/SKILL.md), whose
DragnCards harness is [`references/dragncards.md`](../marvel-champions-play/references/dragncards.md).

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
skill owns taking a hand.

## Guardrails and workflow

Use **spawn, observe, decide, act, report**. A build skill never grants permission to
mutate a live table. The seat guard, turn authority, pending-seat authority, and
illegal-action finding workflow remain in agent-orchestrator; only the coordinating agent
resolves a finding.
