## Context

The current game-service exposes almost every FastAPI route to MCP by building the MCP server directly from the FastAPI app and excluding only a few paths with `RouteMap`. That works well for normal game operations, but it is a poor fit for privileged setup workflows that are useful to HTTP automation and test harnesses but too powerful for an LLM-facing tool surface.

The service also returns DragnCards room state as whatever the backend broadcasts on `current_state`, while action execution is performed through Phoenix `game_action` messages. Upstream DragnCards does not expose a dedicated `export_state` or `load_state` room event, but it does support a `game_action` with action type `set_game`, which replaces the in-memory `game` object. That gives the game-service a viable import primitive if it owns the snapshot format and normalizes the payload correctly.

Finally, the package layout is blurry in two places: the API layer is split across `games.py`, `room_control.py`, and `room_events.py`, and the `session/` package currently mixes session orchestration (`manager.py`, `game_session.py`), DragnCards bootstrap/transport helpers (`http_client.py`), action translation (`actions.py`), exceptions, and card search (`card_db.py`). The requested change is a good point to simplify router layout, put a more general card-catalog abstraction in place, and start separating core game-service logic from DragnCards-specific transport code.

## Goals / Non-Goals

**Goals:**
- Add HTTP endpoints to export a reusable setup snapshot from an active session and load that snapshot back into a session.
- Keep import/export operations out of MCP tool discovery and out of the LLM-facing resource surface.
- Define a snapshot format that can round-trip the currently running game without depending on a new upstream DragnCards API.
- Consolidate game-session HTTP routes so room-control and room-event routers no longer need to exist as separate modules.
- Refactor the `session/` package so orchestration logic is no longer colocated with unrelated transport and catalog helpers.
- Refactor the card search internals toward a plugin-aware catalog abstraction without forcing a broader API redesign in this change.

**Non-Goals:**
- Adding a persistent storage service for saved snapshots.
- Changing the public MCP contract for existing non-privileged game-service tools.
- Introducing full multi-game card ingestion, plugin autodiscovery, or game-specific schema translation for every future plugin.
- Modifying upstream DragnCards backend or plugin code.

## Decisions

### Decision 1: Export and import a versioned snapshot envelope, not the raw `get_state()` response

The HTTP export endpoint will return a versioned snapshot document owned by game-service, for example an envelope containing `schema_version`, `plugin_name`, and a `game` payload. The `game` field will hold the inner DragnCards game map that can be passed back through `set_game`, rather than the entire room state wrapper returned by `get_state()`.

This avoids coupling the import contract to the exact top-level shape of `current_state`, which currently contains more than the mutable `game` object and is not accepted directly by DragnCards `set_game`.

Alternatives considered:
- Return the raw `get_state()` payload and require clients to know how to strip it before import. Rejected because it leaks backend-specific normalization work into every caller and makes round-tripping error-prone.
- Export only a list of higher-level setup actions. Rejected because it would be lossy, harder to generate, and would not capture arbitrary in-progress scenario state.

### Decision 2: Implement import by sending a `game_action` with action type `set_game`

`GameSession` will gain a dedicated state-load method that validates the snapshot envelope, extracts the `game` payload, sends `game_action` with action `set_game`, then refreshes and returns the resulting state. This uses an upstream capability that already exists in DragnCards instead of inventing a service-side replay mechanism.

Alternatives considered:
- Reconstruct imported state by issuing many DragnLang operations such as `LOAD_CARDS`, `MOVE_CARD`, and `SET`. Rejected because it is incomplete, brittle, and far more sensitive to plugin automation side effects.
- Add a new custom room event to DragnCards for state loading. Rejected because this repository does not own the upstream backend contract and the change can be completed without it.

### Decision 3: Keep import/export HTTP-only by excluding specific routes from FastMCP route generation

The new setup endpoints will live in the FastAPI app so they remain normal HTTP routes with request validation and tests, but they will be excluded from FastMCP route generation through explicit `RouteMap` patterns. The result is one HTTP service surface and a narrower MCP surface, without creating a separate internal app.

Alternatives considered:
- Create a second FastAPI app or router tree mounted outside the MCP-backed app. Rejected because it adds structural complexity for little benefit.
- Expose the endpoints to MCP and rely on agent policy not to call them. Rejected because the user explicitly requested that these operations not be available to MPC, and policy-only protection is too weak.

### Decision 4: Consolidate game-session routes into a single router module

The implementation will fold `room_control.py` and `room_events.py` into the core game-session router so all session-scoped operations live together. This matches the existing URL structure, reduces router wiring in `api/app.py`, and makes future MCP inclusion/exclusion decisions easier because there is one place to reason about session endpoints.

Alternatives considered:
- Keep the separate router modules and add more exclusions. Rejected because the current split is already artificial; the endpoints all operate on the same `GameSession` aggregate.
- Create even more router modules for setup/export concerns. Rejected because it would increase fragmentation while the paths remain session-scoped.

### Decision 5: Replace `card_db.py` with a plugin-aware catalog module that preserves current API behavior

The current `/cards` endpoint will keep its outward behavior for Marvel Champions, but the backing module will be refactored from a single hard-coded `card_db.py` loader into a more universal catalog layer keyed by plugin. The first implementation can still ship with only a Marvel Champions provider, but the module boundaries, naming, and lookup flow will no longer assume that every game is backed by the same Cerebro JSON fixture.

Alternatives considered:
- Leave `card_db.py` unchanged and defer the refactor. Rejected because this change already touches setup/import concerns that are closely related to broader game support, and the current naming hard-codes Marvel Champions into the service core.
- Generalize the external API now with mandatory `plugin_name` query parameters and plugin-specific response schemas. Rejected because it is a larger contract change than needed for this proposal.

### Decision 6: Refactor internal package boundaries around responsibilities, not protocol direction names alone

The implementation should separate three concerns that are currently conflated under `session/`:
- service logic and orchestration for active games and snapshot workflows,
- DragnCards-specific inbound/outbound transport and bootstrap helpers,
- card catalog/search providers.

The user suggested names like `outbound/mcp`, `outbound/api`, `inbound/dragncards`, and `logic`. The useful part of that idea is the separation, but using pure inbound/outbound labels everywhere would be misleading because FastAPI and MCP are both external interfaces and DragnCards is both inbound and outbound depending on the event flow. The design should therefore prefer responsibility-oriented boundaries, for example a `logic/` package for session orchestration and a `dragncards/` package for backend-specific transport/bootstrap/catalog adapters, while allowing API and MCP to remain top-level interface packages.

Alternatives considered:
- Leave `session/` mostly as-is and only add new files. Rejected because this change already increases orchestration complexity, and leaving unrelated files together will make the next refactor harder.
- Perform a full package taxonomy rewrite into strict `inbound/` and `outbound/` trees in one pass. Rejected because it is high-churn, risks destabilizing imports, and the directional labels are not consistently clearer than domain-oriented names.

## Risks / Trade-offs

- [Risk] `set_game` is an upstream DragnCards behavior we do not control and it may accept only the inner `game` map, not arbitrary wrappers. [Mitigation] Normalize snapshots inside game-service, validate required top-level keys before sending, and cover the round-trip in integration tests against a live backend.
- [Risk] Loading a snapshot may bypass some plugin initialization paths that normally occur during room creation or reset. [Mitigation] Scope the feature to setup/scenario restoration for an already-created compatible session, and require plugin compatibility checks before import.
- [Risk] Exported snapshots may become incompatible if upstream state shape changes. [Mitigation] Add `schema_version` to the snapshot envelope and fail fast on unsupported versions instead of attempting silent best-effort imports.
- [Risk] Route-level MCP exclusion can drift if endpoint paths are renamed without updating `RouteMap` patterns. [Mitigation] Add unit tests that assert the MCP tool catalogue does not expose import/export operations.
- [Risk] Router consolidation changes internal module boundaries and may create merge friction with nearby work. [Mitigation] Keep the refactor shallow: preserve existing endpoint paths and models while only collapsing module layout.
- [Risk] Internal package refactors can create broad import churn without immediate user-visible value. [Mitigation] Limit the refactor to the modules touched by snapshot import/export and catalog work, keep compatibility imports where needed during the transition, and avoid renaming unrelated top-level interfaces.

## Migration Plan

1. Add the snapshot request/response models and session-layer import/export helpers.
2. Add HTTP endpoints for export/import under the existing `/games/{session_id}/...` path family.
3. Exclude the new endpoints from FastMCP route generation and add regression tests for tool discovery.
4. Collapse the old room-control and room-events router wiring into the main game router without changing public paths.
5. Split `session/` responsibilities into clearer logic, DragnCards adapter, and catalog modules, updating imports incrementally.
6. Replace `card_db.py` internals with a plugin-aware catalog module while keeping the current `/cards` endpoint behavior stable.

Rollback is straightforward because the change is additive at the HTTP contract layer and internal at the router/catalog layer. If import proves unstable, the export/import endpoints can be removed without affecting existing MCP or gameplay actions.

## Open Questions

- Whether snapshot export should include optional metadata such as room slug or replay step for debugging only, or remain limited to data required for reload. Current recommendation: keep the envelope minimal.
- Whether future non-Marvel plugins should reuse the same `/cards` endpoint or introduce plugin-specific discovery endpoints. Current recommendation: keep `/cards` and make plugin-awareness an internal provider concern until a second game requires a public API change.
- Whether the first refactor step should introduce new packages like `logic/` and `dragncards/` immediately, or keep the existing `session/` package as a compatibility facade while moving modules behind it. Current recommendation: use a compatibility facade during implementation to reduce churn.
