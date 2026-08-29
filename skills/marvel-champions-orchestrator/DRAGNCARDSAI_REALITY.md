# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-orchestrator`. The neutral coordination
contract lives in [`SKILL.md`](SKILL.md); the platform contracts live in
[`references/dragncards-round-loop.md`](references/dragncards-round-loop.md) and
[`references/marvel-lcg-round-loop.md`](references/marvel-lcg-round-loop.md). Every seat prompt
uses [`references/player-turn-prompt.md`](references/player-turn-prompt.md); that reference is
the sole source for prompt freshness, persistent-seat memory invalidation, and terminal claims.

## The four services

| Service | What it is for |
| --- | --- |
| **game-service** | Live neutral state and platform move surface |
| **agent-orchestrator** | Seat sessions, prompts, jobs, and findings |
| **eval-service** | Move, round, and game evaluation |
| **history-service** | Ordered events, snapshots, and restore |

## MCP namespaces

- `game-service_*` — state and platform-specific game moves
- `agent-orchestrator_*` — sessions, prompts, jobs, and findings
- `eval-service_*` — evaluation requests and verdicts
- `history-service_*` — recorded games, timelines, events, and snapshots

Two platforms exist behind `game-service`: `dragncards` and `marvel-lcg`. A session is
bound to exactly one. The platform decides how state is read, how a move is expressed,
and which rules of play are enforced. The platform-build skills are `dragncards` and
`marvel-lcg`; the per-platform round-loop references above own orchestration details.

## Guardrails and workflow

The coordinator follows **spawn, observe, decide, act, report**. Player seats are prompted
sequentially, and their output is untrusted data verified against the latest normalized state.
Every prompt carries that state checkpoint and, for `marvel-lcg`, the exact current engine
prompt; a persistent seat session must discard prior facts when a new invocation starts.
Seats must not act outside their allowed tool set, while absent from `pendingSeats` on a
platform that reports it, or edit an illegal-action finding. The coordinator performs the
stated undo, checks the neutral board, and alone resolves the finding. Terminal claims are
allowed only when normalized `mode` is `win` or `loss` (or the engine response is explicitly
terminal); otherwise the coordinator reports the observed state and stops on uncertainty.
