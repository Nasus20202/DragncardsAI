# Support marvel-lcg as a second game platform alongside DragnCards

## Why

DragncardsAI can only play Marvel Champions on DragnCards, and that assumption is welded into
every service. DragnCards is a playtable: it moves cards and runs plugin automation, but it
does not adjudicate rules and it cannot tell an agent which moves are legal. Every illegal
move our agent makes is a move DragnCards was happy to accept.

`marvel-lcg` (the Irefrixs Team's digital Marvel Champions, open-sourced 2026-07-27) is a
rules-enforcing engine. It refuses illegal input and, decisively, **enumerates the legal move
set on request** — `GET /get_ask` returns each available effect with its legal targets, target
count range, and payment options. An agent playing there chooses from a validated list instead
of composing an action and hoping. That is a materially better substrate for both play quality
and move evaluation, and it gives us a second data point for every judgement the eval-service
makes.

Supporting it is also the forcing function for a structural debt we already carry: game-service
has no platform seam at all. `GameSession` and `SessionManager` are typed directly on
`PhoenixClient`/`Channel`/`PhoenixRoom`; `translate_action` is one flat `isinstance` chain; and
`api/enums.py` builds the `GroupId` and `LayoutId` types **at import time** from the Marvel
Champions plugin JSON, so the typed-action layer, the OpenAPI document and every MCP tool schema
are functions of one platform's files on disk. Downstream, `game_id` is a single flat keyspace
underpinning every unique constraint, sequence series, advisory lock and idempotency key in
history-service and eval-service, and there is no `platform` discriminator anywhere in the
repository.

## What Changes

### A platform seam in game-service

- Introduce a `GamePlatform` driver protocol covering the whole platform-specific surface:
  authenticate, create/attach a table, connect, request state, execute a move, seat and
  spectator control, and teardown. `PhoenixRoom` becomes the DragnCards implementation of it.
- `GameSession` and `SessionManager` hold a driver rather than a concrete Phoenix client. Both
  stop constructing DragnCards payloads and stop grepping DragnCards log messages for errors.
- Move state normalisation out of the HTTP router and below `GameSession`, into a per-platform
  normaliser. The four `plugin_name == "marvel-champions"` string branches collapse into one
  polymorphic call.
- Make `GroupId`/`LayoutId` generation lazy and per-platform so the service imports, and serves
  its OpenAPI document, without any one platform's plugin JSON on disk.
- Every session carries a `platform` field, defaulting to `dragncards`.

### A marvel-lcg driver and an enumerated-move surface

- Vendor `z00lus/marvel-lcg` (the maintained "Ronin Edition" fork, the only one with a working
  Linux/Docker path) as a git submodule at `external/marvel-lcg`, pinned to a commit, and run it
  as a compose service on the existing shared network.
- Implement the driver against its documented-by-source HTTP+JSON API: `GET /new` to create a
  game, `WS /ws?p=<seat>` for render frames, `GET /get_world` for the board, `GET /get_ask` for
  legal options, `POST /post` to submit, `GET /client_updated` to acknowledge.
- Add a platform-native agent surface — list the enumerated legal options for the seat, and
  choose one by id with targets and resource payments. marvel-lcg moves are **not** forced into
  the DragnCards typed-action vocabulary.
- Normalise marvel-lcg's `WorldDescriptor` into the same simplified game state the agent already
  reads, honouring its per-seat visibility model so a bot sees exactly what that seat's human
  would.

### A platform discriminator downstream

- history-service: `platform` on events and snapshots, joined into all three unique constraints
  and both `game_id` indexes, on the event envelope, and in the export bundle header.
- eval-service: `platform` on evaluation requests and targets, a per-platform state projection
  and action taxonomy, and a judge prompt that states which platform's rules surface produced
  the move.
- dashboard: platform on the games list, a per-platform game viewer, and per-platform round and
  phase mapping.
- agent-orchestrator: seat and turn authority derived per platform rather than from hardcoded
  DragnCards step ids, and a system prompt that names the platform in play.

### A platform-neutral skill corpus

The ~5,400 lines of Marvel Champions rules and strategy under
`marvel-champions-rules-reference` and `marvel-champions-learn-to-play` contain zero
platform-specific tokens today and stay exactly as they are. The ~1,600 lines of harness
contract concentrated in `marvel-champions-play` and the orchestrator round loop split into a
platform-neutral skill plus per-platform harness references, and a new `skills/marvel-lcg/`
joins the existing `skills/dragncards/`.

### Non-goals

- **Not** modifying either upstream. `external/dragncards` and `external/marvel-lcg` stay
  read-only vendored dependencies.
- **Not** achieving feature parity between the two platforms. DragnCards keeps its typed-action
  and DragnLang surface; marvel-lcg gets enumerated options. Neither grows the other's surface.
- **Not** cross-platform game migration. A recorded game belongs to the platform that produced
  it; snapshots and restores stay within one platform.
- **Not** supporting a third platform, and not building a plugin system. Two implementations of
  one protocol is the goal; a registry of many is not.
- **Not** running marvel-lcg's Windows binary, under Wine or otherwise. We run it from source.
- **Not** loading third-party marvel-lcg card scripts, which execute arbitrary Python.
- **Not** exposing marvel-lcg's `/debug` endpoint through any of our surfaces.
- **Not** using marvel-lcg's client-side MarvelCDB deck import path. Games are set up from the
  decks and scenarios that ship in its repository.

### Modified Capabilities

- `game-service` — the driver protocol, per-platform normalisation, lazy enum generation, the
  `platform` field on sessions, and the marvel-lcg routes and MCP tools.
- `dragncards` — reframed from *the* integration contract to *one platform's* contract.
- `simplified-game-state` — the projection becomes platform-neutral, produced by a per-platform
  normaliser, with marvel-lcg's zones mapped onto it.
- `history-event-store` — the `platform` discriminator, constraints, envelope, and bundle header.
- `agent-move-evaluation` — per-platform state projection, action taxonomy, and judge framing.
- `eval-service` — the `platform` columns and migrations.
- `dashboard` — platform-aware games list and game viewer.
- `game-history-ui` — per-platform round and phase mapping.
- `agent-orchestrator` — per-platform seat and turn authority, platform-aware system prompt.
- `game-orchestration` — a round loop expressed per platform.
- `runtime-skill-corpus` — the neutral/per-platform skill split and the new marvel-lcg skill.
- `marvel-champions-play-skill` — platform-neutral play guidance plus per-platform harness
  references.
- `infrastructure` — the `external/marvel-lcg` submodule, its compose service, and platform
  selection.
- `testing` — integration coverage against a live marvel-lcg instance.
- `observability` — spans and service naming for the new driver.
- `service-mcp-surface` — the enumerated-option tools on game-service's MCP surface.

### Added Capabilities

- `marvel-lcg` — the integration contract with marvel-lcg: auth and version cookies, game
  creation, the render-frame WebSocket, world and ask retrieval, move submission, and the
  hazards a client must defend against.
- `enumerated-game-options` — the platform-neutral contract for an agent surface that lists
  engine-validated legal moves and submits a chosen one.
- `game-platform` — the cross-cutting platform notion: the driver protocol, the `platform`
  discriminator and its default, and what every service must do with it.

### Impact

- **Behaviour for existing DragnCards sessions is unchanged.** `platform` defaults to
  `dragncards` everywhere, including for rows written before this change.
- Two database migrations add columns and widen unique constraints:
  `history-service` `0002` and `eval-service` `0004`, each in both PostgreSQL and SQLite
  dialects.
- A new git submodule means `git submodule update --init --recursive` is mandatory in fresh
  worktrees, which was already true and is now more consequential.
- `marvel-lcg` carries **no LICENSE file** and is a fan implementation of Marvel/FFG
  intellectual property. We rely on the developer's explicit written permission in
  `irefrixs/marvel-lcg` issue #3, we credit the Irefrixs Team, and we never redistribute card
  art — it streams at runtime from Cerebro. The project is sunset, so we depend on a maintained
  fork and pin it.
- `marvel-lcg` ships an unauthenticated `GET /debug` that reaches `exec()` behind a bypassable
  AST blocklist, and the vendored fork binds `0.0.0.0`. It is confined to the internal Docker
  network with a password set, and `/debug` is never proxied.
