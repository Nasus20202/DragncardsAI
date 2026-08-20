# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-rules-reference`. The rules corpus
lives in [`SKILL.md`](SKILL.md) and its `resources/` files; those files are shared across
platforms and this preface does not alter their rules content. Harness details belong to
`marvel-champions-play`'s per-platform references.

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
skill and its harness references own live execution.

## Guardrails and workflow

Use **spawn, observe, decide, act, report** for rules lookups. A rules answer is not
permission to act for a seat or advance a phase. The orchestrator verifies state and
resolves illegal-action findings; a rules reference never edits one.
