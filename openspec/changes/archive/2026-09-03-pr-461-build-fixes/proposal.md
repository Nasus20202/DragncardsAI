## Why

Pull request 461 updates the Marvel Champions plugin to a revision whose automation artifact contains empty `VAR` names. DragnCards rejects those definitions while loading cards, causing the integration suite to fail in unrelated deck and shuffle scenarios. The Game Service also constructs session timestamps with the deprecated naive `datetime.utcnow()` API.

## What Changes

- Pin the Marvel Champions plugin to the last known compatible revision before the malformed automation change.
- Construct default session timestamps as timezone-aware UTC datetimes.
- Add regression coverage for plugin variable names and session timestamp awareness.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-service`: default session creation timestamps are timezone-aware UTC values.
- `testing`: integration coverage validates DragnCards plugin automation variable names.

## Non-goals

- Do not change DragnCards engine behavior or silently ignore invalid plugin operations.
- Do not alter the existing live deck-loading and shuffle integration scenarios.
