# Tasks

## 1. Ordinary startup and singleton engine lifecycle

- [x] 1.1 Remove the Compose profile from the repository-owned `marvel-lcg` and `marvel-lcg-init` services, preserve their health, volume, network, password, and initialization ordering, and make ordinary app/infrastructure startup include both
- [x] 1.2 Update startup helpers, readiness checks, image/build targets, and local environment examples so no normal command requires a Marvel profile while the engine remains an internal backend dependency
- [x] 1.3 Add a Valkey-backed singleton lease keyed by the configured marvel-lcg endpoint, with ownership token, TTL renewal, release, and fencing of mutating calls
- [x] 1.4 Make Marvel creation fail with a conflict when another session owns the active lease, and mark a session degraded without sending moves after lease loss
- [x] 1.5 Reject marvel-lcg attachment explicitly as unsupported rather than treating the service-generated slug as an engine room identifier
- [x] 1.6 Add unit and live integration coverage for ordinary startup, initializer readiness, competing lease claims, lease release, lease loss, and unsupported attachment

## 2. Typed platform creation and neutral setup discovery

- [x] 2.1 Define typed `PlatformCreateSpec` variants for DragnCards and marvel-lcg and change the `GamePlatform` protocol to accept the typed specification instead of `plugin_info`
- [x] 2.2 Add the read-only `list_game_setup_catalog` HTTP route with an explicit operation identifier, strict request schema, platform-discriminated response, and generated neutral MCP tool
- [x] 2.3 Implement per-platform catalog resolution behind the drivers, returning opaque scenario and hero-deck ids plus display metadata without exposing engine file paths as the selection contract
- [x] 2.4 Add the optional typed setup field to `create_game`; validate the platform discriminator, scenario id, ordered unique neutral seats, and hero-deck ids before calling the driver
- [x] 2.5 Preserve omitted-setup compatibility for DragnCards and explicitly configured Marvel defaults, validate defaults against the live catalog, echo the resolved selection, and remove every first-catalog fallback
- [x] 2.6 Add tests proving that two different requested Marvel hero-deck ids produce the corresponding ordered decks and that invalid or missing defaults fail without creating a table
- [x] 2.7 Add integration coverage that discovers a scenario and at least two hero decks through the neutral catalog, creates the requested setup, and verifies the returned state contains the requested heroes in seat order

## 3. Explicit platform capabilities and move surfaces

- [x] 3.1 Add `platform` and `move_surface` to the driver capability contract and to session metadata, create/list/state responses, and the session action catalog
- [x] 3.2 Keep `typed_actions` and raw DragnLang restricted to DragnCards and keep `enumerated_options` restricted to marvel-lcg, with descriptive server-side refusal for the opposite surface
- [x] 3.3 Ensure the neutral setup response and every session-describing MCP result carry the same capability metadata as HTTP
- [x] 3.4 Pin capability metadata and cross-surface refusal behavior in unit tests for both backends

## 4. Correct generated MCP and skill contract

- [x] 4.1 Keep setup discovery and creation on the generated game-service MCP surface with strict root schemas and no hand-written MCP-only behavior
- [x] 4.2 Verify the generated Marvel option schemas use `player_n` for both listing and choosing, and reject the stale `player` argument rather than dropping it
- [x] 4.3 Correct the Marvel play-skill reference to call `list_game_options(session_id, player_n)` and `choose_game_option(session_id, player_n, option_id, targets, resources)` with the current neutral option contract
- [x] 4.4 Update the orchestrator skill setup recipe to discover the catalog, pass the typed scenario and ordered seat/deck selections, and stop on an invalid or absent setup rather than inventing heroes
- [x] 4.5 Add MCP integration coverage proving a backend-neutral client can discover setup, create a selected game, read `platform`/`move_surface`, and use only the advertised move surface

## 5. Documentation, regression checks, and delivery verification

- [x] 5.1 Update the root and service startup documentation, Compose service listings, and environment examples to describe ordinary Marvel startup and the singleton limitation
- [x] 5.2 Update the end-to-end agent instructions with the neutral setup discovery call, typed create example, explicit capability metadata, and the Marvel option argument names
- [x] 5.3 Run the existing DragnCards unit and integration suites unchanged and compare its OpenAPI/MCP schemas before and after the new platform-neutral routes
- [x] 5.4 Run the Marvel live workflow through ordinary startup: discover setup, create the requested heroes, read pending options with `player_n`, choose an option, and verify state advancement
- [x] 5.5 Run `openspec validate --all` and archive this change only after every requirement, task, and affected main specification is synchronized
