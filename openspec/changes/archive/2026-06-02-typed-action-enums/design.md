## Context

Typed action request/response models in the game-service are currently defined with free-form string fields for values that are effectively bounded by the Marvel Champions plugin (e.g., group IDs, player identifiers, layout IDs). These models are exposed via HTTP and MCP JSON Schema, which means clients do not receive enumerated constraints and invalid values reach runtime validation or DragnCards errors. The system is scoped to Marvel Champions only for this change.

## Goals / Non-Goals

**Goals:**
- Define explicit enum types for Marvel Champions–specific string fields in typed action request/response models.
- Ensure OpenAPI/MCP schemas include enum constraints for these fields.
- Improve validation errors and test coverage for invalid enum values.

**Non-Goals:**
- Generalizing enums across multiple plugins.
- Changing DragnCards backend group definitions or automation.
- Dynamic discovery of enum values at runtime.

## Decisions

- **Decision:** Introduce explicit enum classes for Marvel Champions group IDs, player identifiers, and layout IDs in game-service action models.
  - **Alternatives considered:**
    - Keep strings and validate with regex/prefix rules only.
    - Load enums dynamically from plugin metadata at runtime.
  - **Why rejected:**
    - Regex/prefix rules are too loose and still allow invalid group IDs.
    - Runtime enum discovery adds complexity and coupling to plugin files and runtime state; the change is explicitly scoped to Marvel Champions only.

- **Decision:** Apply enums directly in Pydantic models (request/response) so OpenAPI and MCP schemas reflect constraints automatically.
  - **Alternatives considered:**
    - Enforce enums only in custom validation logic without changing types.
    - Add enums only in response models and keep request models permissive.
  - **Why rejected:**
    - Custom validation would not surface in schema clients and would duplicate logic.
    - Partial enum usage leads to inconsistent schemas and validation behavior.

- **Decision:** Use a curated, static list of Marvel Champions group IDs derived from the plugin's groups.json as the source of truth for enums.
  - **Alternatives considered:**
    - Infer from runtime game state or load-groups APIs.
    - Maintain a smaller, handpicked subset of common groups only.
  - **Why rejected:**
    - Runtime inference is not guaranteed at request validation time and adds IO.
    - A partial list would cause false negatives for legitimate groups.

## Risks / Trade-offs

- **Risk:** Plugin group IDs could change upstream, making enums stale. → **Mitigation:** Document the source (groups.json) and add a test to verify enum values are a subset of known plugin groups.
- **Risk:** Enum tightening could reject previously accepted but invalid client input. → **Mitigation:** Treat as intentional validation improvement; include explicit error examples in tests and release notes.
- **Risk:** DragnCards backend allows dynamic or custom groups not in the plugin files. → **Mitigation:** This change is scoped to Marvel Champions only, and we will not accept dynamic groups in typed actions.
