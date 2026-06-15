## Context

The MCP interface in game-service exposes game-room management endpoints alongside core session and action controls. The proposal narrows MCP to a simplified flow where POST /games creates a room and seats the model in the first available player slot, and POST /games/attach attaches to an existing room and assigns the model to the first available seat. This is a cross-cutting change affecting MCP tool exposure, documentation, and tests, while leaving REST endpoints and DragnCards backend behavior unchanged.

## Goals / Non-Goals

**Goals:**
- Remove MCP game-room management endpoints (spectator, replay, player-count, seat assignment, and similar) from the exposed tool surface.
- Make POST /games and POST /games/attach the MCP entry points for initial seating behavior.
- Keep HTTP REST endpoints intact while aligning MCP documentation with the simplified surface.

**Non-Goals:**
- Alter DragnCards backend room or seating behavior.
- Change non-MCP REST API contracts or WebSocket protocol usage.
- Add new MCP capabilities beyond the streamlined flow.

## Decisions

- **Decision:** De-scope MCP tools to exclude game-room management, leaving those capabilities only in REST (if they exist) or as internal calls. 
  **Alternatives considered:**
  - Keep MCP endpoints but mark them deprecated. Rejected because it preserves a large surface area and ambiguity about the expected model flow.
  - Remove REST endpoints alongside MCP. Rejected because the request targets MCP only and REST clients may still need them.

- **Decision:** Treat POST /games and POST /games/attach as MCP entry points that guarantee first-available-seat assignment. 
  **Alternatives considered:**
  - Add a new MCP tool specifically for seating. Rejected because seating is already implicit in room creation and attachment and would reintroduce complexity.
  - Require a follow-up MCP call to claim a seat. Rejected because it adds round trips and contradicts the desired streamlined model flow.

- **Decision:** Update MCP docs/tests to enforce the reduced endpoint set, without changing the underlying SessionManager behavior beyond ensuring the seat assignment occurs on room creation. 
  **Alternatives considered:**
  - Add guardrails that throw errors for removed endpoints at runtime. Rejected because they should no longer be exposed at all through MCP.
  - Rely only on docs and leave MCP registration untouched. Rejected because it allows accidental use and breaks the intended contract.

## Risks / Trade-offs

- **Risk:** MCP clients depending on removed endpoints will break → Mitigation: Mark as breaking in proposal, update docs, and include removal in release notes.
- **Risk:** Upstream DragnCards seating behavior differs from assumptions (first available seat) → Mitigation: Confirm current behavior in game-service integration tests and document expectations in specs.
- **Trade-off:** Reduced MCP flexibility (no spectator mode or replay controls) → Mitigation: Keep REST endpoints for operator workflows if still needed.
