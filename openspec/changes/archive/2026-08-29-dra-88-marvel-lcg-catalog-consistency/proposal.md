## Why

The Marvel LCG setup catalog returns opaque hero-deck identifiers that can be rejected by the subsequent game-creation request when the engine represents the same document path with a different harmless `./` prefix. This makes a freshly discovered setup unusable and incorrectly suggests that the caller supplied a stale or invalid identifier.

## What Changes

- Make Marvel LCG catalog identifier resolution tolerant of equivalent engine document-path spellings while retaining the opaque identifier contract.
- Ensure identifiers returned by `list_game_setup_catalog` remain accepted by `create_game` when the engine's listing changes only the leading relative-path notation between requests.
- Continue rejecting arbitrary document paths, display names, unknown identifiers, and identifiers absent from the live catalog.
- Add regression coverage for the reported Spider-Man starter-deck identifier and for the unknown/path rejection boundaries.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marvel-lcg`: require stable cross-request catalog identity resolution for equivalent engine document paths.

## Non-goals

- Do not change the Marvel LCG engine's file listings or opaque ID format returned to clients.
- Do not allow file paths, display names, or arbitrary hashes as create-game inputs.
- Do not bypass the singleton-engine lease or alter active-session lifecycle behavior.
- Do not change the engine's scenario or hero document contents.