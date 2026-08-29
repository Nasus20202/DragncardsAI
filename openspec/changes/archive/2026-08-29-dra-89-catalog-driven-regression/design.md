## Context

The existing Marvel LCG regression in `services/game-service/tests/unit/test_neutral_setup.py` already simulates discovery and creation listings with equivalent path spellings. Its creation spec should model the public contract: IDs are opaque values produced by discovery, not values reconstructed by the test.

## Goals / Non-Goals

**Goals:**

- Exercise all scenario and hero-deck entries returned by setup discovery.
- Verify the exact catalog IDs flow into creation and remain opaque.
- Keep the raw-path rejection test independent.

**Non-Goals:**

- Change production identifier resolution.
- Add a live-engine dependency or create/delete a game during verification.

## Decisions

- Build the creation selection from `catalog["scenarios"]` and `catalog["hero_decks"]` returned by `setup_catalog`; this is the only accepted source for creation inputs in the regression.
  - Rejected alternative: hardcode the known Spider-Man hash, because that can pass while catalog and validation disagree for other entries.
- Keep source paths in the mocked engine listings and assert fetched paths/content separately; paths model the engine response, while IDs model the public API boundary.
  - Rejected alternative: assert only that creation succeeds, because it would not prove every listed ID was passed through.
- Retain one opaque-prefix assertion and the raw-path rejection test.
  - Rejected alternative: remove all shape assertions, because the test should still explicitly guard against exposing filesystem paths as setup identities.

## Risks / Trade-offs

The mock does not exercise upstream WebSocket behavior or the singleton lease. This is intentional: the change is test coverage for HTTP setup identity flow, and live creation would mutate shared engine state. The mocked two-listing sequence continues to cover the upstream path representation drift without relying on external availability.
