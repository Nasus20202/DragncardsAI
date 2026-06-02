## Context

The game-service already exposes session-scoped actions and plugin metadata over HTTP and MCP. It also already knows how to load cards into a session through `load_cards`, and the Marvel Champions plugin has prebuilt deck data available from its plugin fixtures and JSON metadata.

This change adds a session-specific deck-loading operation for LLM clients. The operation should behave like the frontend's "Load prebuilt deck" flow, but the tool must be explicit about the target session and deck id so it remains safe and deterministic.

## Goals / Non-Goals

**Goals:**
- Load a prebuilt deck into an existing game session by deck id.
- Make the tool session-scoped and explicitly tied to the Marvel Champions plugin.
- Reuse the same underlying deck-loading source of truth as the existing plugin/front-end path.
- Expose the new capability through MCP tool discovery.

**Non-Goals:**
- No new deck catalog or search UI.
- No changes to DragnCards backend behavior.
- No generic cross-plugin deck-loader abstraction.
- No changes to session creation or room attachment semantics.

## Decisions

1. Add a dedicated session-action endpoint/tool for prebuilt deck loading rather than extending generic `load_cards`.
   - Rationale: a prebuilt deck load is higher-level than raw card loading and needs plugin-specific selection by deck id.
   - Alternatives considered: add `deck_id` to `load_cards`. Rejected because it would overload a generic card-loading action with plugin-specific semantics.

2. Keep the tool Marvel Champions-specific for now.
   - Rationale: the existing deck-loading source of truth and frontend behavior are plugin-specific, and the current implementation only has one supported plugin path.
   - Alternatives considered: make the tool provider-agnostic. Rejected because there is no evidence of a stable cross-plugin deck-loading contract yet.

3. Resolve the deck id through the plugin data layer and then execute the existing session action pathway.
   - Rationale: the plugin already owns prebuilt deck metadata and the game-service already owns session execution.
   - Alternatives considered: call DragnCards directly from MCP. Rejected because it would duplicate session logic and bypass the existing session manager.

4. Use a single success response with the session id.
   - Rationale: callers care that the session was updated, not the internal deck-loading mechanics.
   - Alternatives considered: return a full deck manifest. Rejected because that adds response weight without changing the workflow.

## Risks / Trade-offs

- [Upstream deck metadata drift] -> The plugin's prebuilt deck format or ids may change. Mitigation: read from the plugin-owned metadata and cover the loader with fixture-backed tests.
- [DragnCards loading semantics] -> The frontend flow may rely on side effects or ordering that are not obvious from the deck id alone. Mitigation: reuse the same session action path used by other plugin-driven loads and verify against the plugin fixture shape.
- [Session state mismatch] -> Loading a deck into a session that is not ready could partially mutate the room. Mitigation: execute under the session lock and return a clear error if the session is unavailable.

## Migration Plan

1. Add the deck-loading helper in the Marvel Champions plugin/provider layer.
2. Add the new session-scoped MCP tool and route it through the session manager.
3. Add tests covering successful load, invalid deck id, and missing session behavior.
4. Verify the tool is visible in MCP discovery and does not alter unrelated session actions.

Rollback is straightforward: remove the MCP tool and the session loading helper. No persistent data migration is required.

## Open Questions

- Should the deck-loading tool return only success, or should it also return a small summary of the loaded deck?
- Should the tool accept `player_n` explicitly, or always target the current session's active player context?
