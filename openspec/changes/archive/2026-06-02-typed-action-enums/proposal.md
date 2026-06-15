## Why

Typed game action request/response models currently use free-form strings for fields that are effectively bounded by Marvel Champions plugin group IDs, player seats, and action-specific enum-like values. This makes invalid inputs easy and forces downstream validation. Defining enums improves correctness, tooling, and documentation while the system is scoped to the Marvel Champions plugin.

## What Changes

- Introduce enum types for bounded string fields in typed action request/response models (e.g., group IDs, player identifiers, player count layouts, and other MC plugin–specific literals).
- Update action schema/catalog exposure so OpenAPI/MCP schemas reflect these enums for validation and client guidance.
- Add/adjust tests to validate enum constraints and error behavior for invalid values.

## Capabilities

### New Capabilities
- (none)

### Modified Capabilities
- `game-service`: Tighten typed action schemas to use enum values for Marvel Champions plugin inputs/outputs.

## Impact

- services/game-service action models, schema generation, and MCP tool schemas
- OpenAPI/JSON Schema consumers (stricter validation)
- Tests covering action validation and schema exposure

## Non-goals

- Supporting enum sets for non-Marvel Champions plugins
- Changing DragnCards backend behavior or plugin definitions
- Introducing dynamic or plugin-agnostic enum discovery at runtime
