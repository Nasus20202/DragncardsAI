# Start marvel-lcg with the stack and make game setup platform-neutral

## User report

> "okay, so the marvel lcg should start up together with the app, not some docker profile etc. also, the game is always created with the same heroes, not matter what was prompted. the mcp should be backend agnostic, but should work correctly."

## Why

The repository already contains a marvel-lcg driver, but the engine and its initialization
container are hidden behind a Compose profile. A normal application startup therefore cannot
create a marvel-lcg game, and a caller has to know an infrastructure detail before it can use the
platform.

Game creation also currently lets platform-specific defaults win over the caller's requested
heroes. In particular, the marvel-lcg driver can fall back to the first catalog entries, so a
prompt that names a different scenario or hero deck does not necessarily affect the created game.
The setup input crosses the platform seam as an untyped `plugin_info` mapping, which makes this
failure easy to introduce and difficult for an MCP client to discover.

Finally, the MCP surface is generated from HTTP routes, but the platform capabilities and the
Marvel option tool argument names are not explicit enough for a backend-agnostic caller. A neutral
setup catalog, a typed platform create specification, and explicit platform/move-surface metadata
let one client discover setup and then use the move surface that the selected backend actually
provides.

## What changes

- Start the marvel-lcg engine and its initialization service during ordinary application and
  infrastructure startup; selecting a Compose profile is no longer required.
- Add a neutral setup discovery endpoint and generated MCP tool that returns platform-tagged,
  opaque scenario and hero-deck identifiers.
- Add an optional discriminated, typed setup specification to `create_game`. A marvel-lcg setup
  carries one `scenario_id` and an ordered list of `{seat, hero_deck_id}` entries.
- Keep legacy setup calls working when setup is omitted, while removing silent first-catalog
  selection. A configured legacy default must resolve through the catalog and be echoed in the
  response; otherwise creation fails with an actionable request error.
- Replace the platform seam's untyped create mapping with a typed platform create specification.
- Return explicit `platform` and `move_surface` metadata and keep DragnCards typed actions and
  marvel-lcg enumerated options as separate capability-specific surfaces.
- Coordinate marvel-lcg's singleton engine with one active lease and reject unsupported external
  attachment instead of pretending that a local slug is an engine room identifier.
- Make the generated MCP contract backend agnostic, including the exact `player_n` argument used
  by the Marvel option tools and the neutral setup tool.

## Modified capabilities

- `game-platform` — typed platform-owned creation specs and explicit capability metadata.
- `game-service` — neutral setup discovery, typed creation, setup compatibility, metadata, and
  singleton-engine lifecycle.
- `infrastructure` — ordinary startup includes marvel-lcg and its initialization service.
- `marvel-lcg` — catalog identifiers, selected setup, and singleton attachment constraints.
- `service-mcp-surface` — neutral generated setup tool and strict, correct platform option schemas.
- `game-orchestration` — setup is discovered and selected rather than hardcoded by a prompt.
- `marvel-champions-play-skill` — Marvel option calls use the route's actual argument names.
- `testing` — startup, setup selection, capability metadata, MCP, and singleton lease coverage.

## Non-goals

- No change to Marvel Champions rules content or to the two existing move surfaces.
- No translation of DragnCards typed actions into marvel-lcg options, or of marvel-lcg options into
  DragnCards actions.
- No support for a third game platform or a general plugin registry.
- No cross-platform game migration, arbitrary MarvelCDB imports, or exposure of the engine debug
  endpoint.
- No modification of vendored upstream engine source.
