## 1. Catalog Data Model

- [x] 1.1 Add a prebuilt set catalog parser/service backed by the Marvel Champions `sets.json` fixture data.
- [x] 1.2 Define the normalized set summary shape with `id`, `name`, and `type` fields and basic name/type filtering.

## 2. Service Exposure

- [x] 2.1 Add FastAPI routes for listing and filtering prebuilt sets so the catalog is available through the existing game-service HTTP surface.
- [x] 2.2 Ensure MCP discovery exposes the new set catalog tools alongside the existing card catalog tools.

## 3. Tests

- [x] 3.1 Add unit tests for the set catalog service parser and filter behavior.
- [x] 3.2 Add API tests covering successful list/filter responses and empty-result handling.
- [x] 3.3 Update MCP tool discovery tests to include the new prebuilt set catalog tools and preserve the existing exclusions.
