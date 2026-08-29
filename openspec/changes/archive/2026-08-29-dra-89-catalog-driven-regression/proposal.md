## Why

The shipped Marvel LCG regression proves one selected ID can survive an engine path spelling change, but it still hardcodes the expected Spider-Man identifier. That leaves catalog/validation drift undetected when the catalog emits a different opaque identifier or when another listed setup entry is mishandled.

## What Changes

- Make the path-spelling regression obtain scenario and hero-deck IDs from the catalog response.
- Pass every catalog-returned scenario and hero-deck ID directly into the creation spec without reconstructing or hardcoding IDs.
- Keep assertions that the values are opaque and that raw filesystem paths remain rejected.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `marvel-lcg`: clarify that catalog identifiers are passed through unchanged from discovery to creation, and cover that contract with regression evidence.

## Non-goals

- No runtime catalog or identifier-resolution behavior changes.
- No changes to engine leasing, game creation APIs, or live game state.
- No removal of the focused reported-ID hash assertion where it documents the catalog contract; this change only removes its role as the creation input.
