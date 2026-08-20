---
name: marvel-lcg
description: Build and debug the marvel-lcg platform adapter and its HTTP/WebSocket protocol; not a game-playing skill.
metadata:
  platform: "marvel-lcg"
  version: "1.0"
---

## Scope: this is not a play skill

This skill documents the `marvel-lcg` platform implementation: its engine transport,
normalised data, packaging, and adapter hazards. It is not permission to act on a live
game and contains no Marvel Champions rules. For play, load `marvel-champions-play`; for
cooperative scheduling, load `marvel-champions-orchestrator`; for rules, load the shared
`marvel-champions-rules-reference` skill.

## Platform contract

The maintained Ronin Edition fork is a Python + aiohttp rules engine with a thin client.
The adapter authenticates, obtains the version cookie, creates a game, connects the
render-frame WebSocket, announces the client, reads world and ask data, and exposes the
normalised state and enumerated game options through `game-service`.

- Neutral seats are `player1` through `player4`; the adapter maps `playerN` to the
  platform's zero-based seat at the transport edge.
- Options are identified by stable ids, not names. The option's target range and resolved
  card targets are part of the agent-facing contract.
- The engine's phase is prose and its step id is an opaque monotonic integer. Consumers
  use neutral `phase`, `phaseLabel`, `playRound`, `players`, and `zones`.
- The client submits `{id, targets, resources}` and observes the state that follows;
  the platform's successful response does not itself prove that the move was accepted.

## Hazards that must be defended

- Invalid input is retried by the engine without bound. The adapter owns a bounded
  submission-attempt cap and stuck-prompt detection; tests must never retry forever.
- `POST /post` acknowledges input without reporting validity. A rejected input is
  silently discarded and the same prompt can be asked again. Confirm progress from the
  subsequent state and prompt, not from HTTP 200.
- The unauthenticated `/debug` endpoint reaches arbitrary code execution. It must never
  be called, composed into a URL, exposed through game-service, exposed through the
  dashboard proxy, or reachable from the deployed platform surface.
- Card scripts are executable Python. Do not load third-party card packs or scripts;
  use only the pinned, reviewed content shipped with the platform integration.
- The render frame can repeat a prior `render_id`; liveness is keyed by the complete
  prompt tuple, not by render id alone. Coalesce frames and emit history only for prompts
  and completed moves, never for every frame.

## Runtime boundary

The platform build skill is for adapter and engine work outside a live hand. The
platform-neutral play contract is owned by `marvel-champions-play/references/marvel-lcg.md`;
do not duplicate play recipes or rules here.
