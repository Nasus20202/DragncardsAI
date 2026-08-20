# DragncardsAI reality — how this skill sits in the runtime

This file is the meta-context for `marvel-champions-play`. The neutral play contract
lives in [`SKILL.md`](SKILL.md). Platform contracts live in
[`references/dragncards.md`](references/dragncards.md) and
[`references/marvel-lcg.md`](references/marvel-lcg.md); load exactly one for the session's
platform. The shared Marvel Champions rules and learn-to-play skills remain single-sourced.

## The four services

Every game runs through the four first-party services below, each with HTTP and MCP at
`/mcp`:

| Service | What it is for |
| --- | --- |
| **game-service** | Live state and the platform's game move surface |
| **agent-orchestrator** | Sessions, prompts, jobs, seat guards, and findings |
| **eval-service** | Move, round, and game evaluation through the judge |
| **history-service** | Ordered events, snapshots, and restore |

## MCP namespaces

- `game-service_*` — state and platform-specific game moves
- `agent-orchestrator_*` — sessions, prompts, jobs, and findings
- `eval-service_*` — evaluation requests and verdicts
- `history-service_*` — recorded games, timelines, events, and snapshots

Two platforms exist behind `game-service`: `dragncards` and `marvel-lcg`. A session is
bound to exactly one. The platform decides how state is read, how a move is expressed,
and which rules of play are enforced. The platform-build skills are `dragncards` and
`marvel-lcg`; this play skill owns taking a hand. The harness references named above own
each platform's move contract.

## Seat guardrails and workflow

1. **Spawn** — the coordinator creates a session and seat agent.
2. **Observe** — read neutral game state before every decision and read job events when
   the coordinator asks what a seat did.
3. **Decide** — use the shared rules and the one loaded platform harness reference.
4. **Act** — use only the platform's allowed game-service tools and only when the platform
   is asking this seat.
5. **Report** — describe the observed result; the coordinator owns phase control and
   resolves findings.

The seat guard refuses foreign-seat identifiers and foreign owned zones before dispatch.
Do not call tools outside the platform's move surface, do not advance a turn where the
platform advances it implicitly, and do not edit an illegal-action finding recorded
against the seat through `report_illegal_action`. Perform its stated undo and report it;
only the coordinating agent closes it.
