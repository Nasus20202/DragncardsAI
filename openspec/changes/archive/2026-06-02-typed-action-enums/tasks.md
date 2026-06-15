## 1. Enum Foundations

- [x] 1.1 Inventory typed action models and identify string fields eligible for Marvel Champions enums
- [x] 1.2 Extract Marvel Champions group IDs, player identifiers, and layout IDs into enum definitions

## 2. Model Updates and Schema Exposure

- [x] 2.1 Update Pydantic request/response models to use the new enum types (SetPlayerCount and PluginPlayerCountLayout)
- [x] 2.2 Ensure OpenAPI/MCP schema generation reflects enum constraints (added schema test)

## 3. Validation and Coverage

- [x] 3.1 Add unit tests for enum validation errors on invalid values
- [x] 3.2 Add schema exposure tests to confirm enum values are present in tool schemas
