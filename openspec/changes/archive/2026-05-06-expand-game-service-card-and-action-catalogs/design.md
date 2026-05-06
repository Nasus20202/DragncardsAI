## Context

The current game-service card catalog is intentionally minimal: the Marvel Champions provider normalizes only a handful of fields from `fixtures/cerebro/cards.json` into `CardResult`, even though the source data contains gameplay-relevant metadata such as uniqueness, cost, attack, thwart, defense, health, hand size, recover, boost, acceleration, scheme values, resource, rules text, authorship, and printing-level details. That forces callers to make decisions with incomplete data even though the provider already has access to the richer source JSON.

The action catalog has a different problem. `GET /actions` and `GET /games/{session_id}/actions` currently expose the same typed action schemas and curated raw DragnLang ops, with the per-session endpoint only adding `load_groups`. That does not describe the real plugin-specific affordances an agent can use for a given session, such as Marvel Champions named action lists, hotkeys, touch bar actions, or player-count layouts.

Upstream DragnCards exposes plugin records at `/api/v1/plugins/raw/:plugin_id`. The payload includes `game_def` and `card_db`, which may be useful as a runtime metadata source. However, the game-service must also work in local/offline test flows where the upstream HTTP service or plugin registration may not be available, and we do not control the stability of the upstream payload beyond what is currently implemented.

## Goals / Non-Goals

**Goals:**

- Expose a richer, normalized card search response that includes the relevant fields already present in provider source data
- Make `GET /actions` represent the generic action surface supported by the game-service and DragnCards integration, independent of a specific plugin session
- Make `GET /games/{session_id}/actions` return the global catalog plus plugin-specific action metadata and related affordances for the session's plugin
- Keep plugin-specific catalog generation provider-driven so new plugins can register metadata extractors without editing API routers
- Use upstream plugin metadata when it is available and helpful, without making the catalog unusable when that endpoint is unavailable

**Non-Goals:**

- Executing named plugin action lists directly through new HTTP action types in this change
- Generalizing catalog extraction for every DragnCards plugin format beyond what the provider interface can support
- Mirroring every field in the upstream card JSON if it has no clear gameplay, search, or loading value
- Changing the DragnCards backend or Marvel Champions plugin repositories

## Decisions

### Decision 1: Introduce an explicit provider interface for catalog integrations

The provider layer under `services/game-service/src/game_service/catalog/providers/` will move from ad hoc metadata dictionaries to an explicit provider contract, implemented as a small interface/protocol/base class plus a registry. Each provider will be responsible for turning plugin source data into API-safe metadata and will expose:

- card search filters and search function
- normalized card result projection
- plugin-specific action metadata extraction
- load-group and player-count metadata

This keeps API routers thin, makes plugin-specific behavior additive, and lowers the cost of introducing a new provider because the required hooks are obvious and testable.

Alternative considered: keep card metadata in providers but hard-code action metadata assembly in `api/routers/game_actions.py`.
Rejected because it would split plugin knowledge across the service and make each new plugin require router changes.

Alternative considered: put all metadata assembly into a generic service layer with no provider hooks.
Rejected because the input formats differ by plugin, and a generic parser would either be too weak or too coupled to Marvel Champions conventions.

Alternative considered: keep the current registry of plain dictionaries and just document the expected keys better.
Rejected because it still relies on convention rather than an explicit interface, making it easier for new providers to miss required capabilities or diverge in structure.

### Decision 2: Treat the global action catalog as generic and the session action catalog as an additive overlay

`GET /actions` will continue to expose the generic typed action wrappers plus the curated generic DragnLang operation catalog. It will not include plugin-specific named actions, plugin layouts, or session-specific load-group information.

`GET /games/{session_id}/actions` will return the same global action entries and add a separate plugin metadata section that includes the plugin-defined affordances relevant to that session, such as named action lists, hotkeys, touch-bar actions, default card actions, player-count layouts, and curated load groups.

Alternative considered: keep a single flat `actions` list and append plugin actions as if they were executable typed actions.
Rejected because named plugin action lists are not the same contract as the typed execute-action payloads, and flattening them together would blur which items are directly executable through `POST /games/{id}/actions`.

Alternative considered: make `GET /actions` require a plugin query parameter.
Rejected because the endpoint is explicitly useful as a generic discovery surface, and session-scoped plugin metadata already has a natural home.

### Decision 3: Expand card results as a normalized superset with optional fields instead of returning raw plugin records

The API will expose a stable, normalized `CardResult` model that adds optional fields for the important gameplay and identification data already present in the Marvel Champions base JSON and printings, such as card code/source identifiers, uniqueness, stats, text, resource, author, and printing metadata. Providers will map their raw data into this model and may leave unsupported fields null.

Alternative considered: return raw `card_db` or fixture records directly.
Rejected because upstream payloads are plugin-specific, inconsistent across sources, and harder to document, validate, and evolve safely.

Alternative considered: add only one or two extra Marvel Champions fields now.
Rejected because it would preserve the current piecemeal problem and require repeated model churn as new missing fields are discovered.

### Decision 4: Use local provider data as the primary source, with optional upstream plugin endpoint fallback

For Marvel Champions, the provider will continue to read local checked-in plugin data for deterministic tests and offline development. The design should allow an optional enrichment path that can read `/api/v1/plugins/raw/:plugin_id` when a session already knows the plugin ID and the HTTP endpoint is reachable. That endpoint exposes `game_def` and `card_db`, which can be used to verify or supplement local metadata, but local provider data remains the baseline.

Alternative considered: switch entirely to `/api/v1/plugins/raw/:plugin_id` for plugin metadata.
Rejected because it adds a runtime dependency on upstream HTTP availability and authenticated plugin registration for functionality that can already be derived locally.

Alternative considered: ignore the upstream endpoint entirely.
Rejected because it may provide fresher runtime metadata and is worth supporting as a best-effort source where available.

### Decision 5: Model plugin-defined actions as descriptive metadata, not new execute-action primitives

Named action lists, hotkeys, touch bar entries, and default card actions will be exposed as descriptive catalog metadata that references the underlying DragnLang action list or named action list ID. The execute-action contract remains the existing typed wrappers plus `raw`.

Alternative considered: add a new `plugin_action` typed action that executes named action lists directly.
Rejected because the user asked for better catalog coverage, not a new execution contract, and the safety/parameter model for executing plugin-defined actions needs its own design.

## Risks / Trade-offs

- [Provider interface becomes too broad and hard to implement] -> Mitigation: keep the interface focused on catalog concerns only, with optional hooks for plugin-specific metadata that providers can return as empty collections when unsupported.
- [Provider model grows beyond simple search metadata] -> Mitigation: keep the provider contract declarative and limited to catalog concerns rather than moving unrelated session logic into providers.
- [Expanded `CardResult` could expose noisy or sparsely populated fields] -> Mitigation: add only fields with clear gameplay, loading, identification, or UX value; keep them optional and document them in OpenAPI.
- [Plugin JSON structures are not fully uniform even within DragnCards] -> Mitigation: make extraction provider-specific and normalize to a stable response model.
- [Upstream `/api/v1/plugins/raw/:plugin_id` payload shape is not a formal contract we control] -> Mitigation: use it as optional enrichment/fallback, not as the only source required for catalog generation.
- [Global and per-session action catalogs can drift if both are assembled separately] -> Mitigation: build the per-session response by composing the same global catalog builder plus provider overlay metadata.
- [Named plugin actions may look executable even when extra game context is required] -> Mitigation: keep plugin actions in a separate metadata section with descriptions that clarify they are plugin-defined affordances, not guaranteed safe typed API calls.

## Migration Plan

1. Add the explicit provider interface and adapt the registry to use it.
2. Update Marvel Champions provider to implement the interface, project richer card fields, and extract plugin action metadata from local plugin JSON.
3. Compose per-session action responses from the global catalog plus provider/session overlay data.
4. Optionally add best-effort upstream plugin metadata fetch support where session/plugin context makes it possible.
5. Update unit tests and OpenAPI assertions for the new response shapes.

Rollback is straightforward: revert to the previous response models and provider registry behavior. No persisted data migration is required.

## Open Questions

- Which exact card fields should be considered part of the first stable normalized superset versus deferred until a later change if they are rarely populated?
- Should the per-session action response include raw DragnLang code snippets for plugin-defined actions, or only names/labels and references to source action lists?
- If upstream plugin metadata and local fixture data disagree, should the service prefer local deterministic data, upstream runtime data, or expose both provenance and resolved values?
