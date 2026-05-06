## 1. Provider Metadata Model

- [x] 1.1 Add an explicit provider interface or protocol for catalog integrations under `catalog/providers/`
- [x] 1.2 Adapt the provider registry to register implementations of that interface instead of ad hoc metadata dictionaries
- [x] 1.3 Define normalized data structures for plugin-specific action metadata, including named action lists, hotkeys, touch-bar actions, default actions, and player-count layouts
- [x] 1.4 Keep provider metadata assembly independent from FastAPI router code so new plugins can register metadata without route-specific branching

## 2. Marvel Champions Provider Implementation

- [x] 2.1 Update the Marvel Champions provider to implement the new provider interface
- [x] 2.2 Expand the Marvel Champions provider card normalization to include the relevant gameplay and identification fields from `fixtures/cerebro/cards.json`
- [x] 2.3 Preserve the existing `database_id` behavior and deduplication while adding printing-level metadata needed for loading and identification
- [x] 2.4 Add or update unit tests for the Marvel Champions provider so interface conformance, expanded fields, and current filters all behave correctly

## 3. Marvel Champions Action Catalog

- [x] 3.1 Parse Marvel Champions plugin JSON metadata needed for per-session catalogs, including `actionLists.json`, `hotkeys.json`, `touchBar.json`, `defaultActions.json`, and `playerCountMenu.json`
- [x] 3.2 Normalize that plugin metadata into provider-defined action catalog structures that can be exposed safely through the API
- [x] 3.3 Add or update unit tests for the Marvel Champions provider metadata extractor covering named actions, hotkeys, touch-bar entries, layouts, and load-group output

## 4. Global And Session Action Endpoints

- [x] 4.1 Update the global `GET /actions` response model and builder so it represents only generic typed actions and generic DragnLang operations
- [x] 4.2 Update the per-session `GET /games/{session_id}/actions` response model and router to return the global catalog plus plugin-specific metadata from the provider layer
- [x] 4.3 Ensure unknown or unsupported plugins still return the generic catalog with empty plugin-specific metadata collections instead of failing
- [x] 4.4 Add or update endpoint tests for `GET /actions` and `GET /games/{session_id}/actions` to verify the separation between generic and plugin-specific metadata

## 5. Metadata Source Implementation

- [x] 5.1 Choose the metadata source strategy for plugin-specific catalogs in the provider layer
- [x] 5.2 If upstream plugin metadata is used, keep it as an implementation detail that does not change the documented API contract
- [x] 5.3 Add focused tests for the chosen metadata source strategy so catalog responses remain stable

## 6. API Models And Documentation

- [x] 6.1 Expand `CardResult` and related response models to document the richer normalized card metadata shape
- [x] 6.2 Add response model fields for plugin-specific action metadata on the per-session action endpoint without implying those items are new execute-action primitives
- [x] 6.3 Update OpenAPI assertions to cover the richer card schema and the split between global and per-session action catalogs
