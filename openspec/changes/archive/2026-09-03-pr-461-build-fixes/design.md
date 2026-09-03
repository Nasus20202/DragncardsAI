## Decision

The plugin submodule is pinned to `b9f75148b7c56faac53173d89a04401f0a9f78ed`, the parent of the upstream revision that introduced 227 empty `VAR` names. This preserves the previously passing plugin behavior while avoiding a parent-repository vendoring or runtime patch of third-party JSON.

`GameSession` uses a small named default factory around `datetime.now(timezone.utc)`, matching the timezone-aware timestamp handling already used by `SessionManager` and history emission.

The live API integration module checks the plugin artifact because it is the same artifact copied into the DragnCards container. The unit regression test checks only the Game Service session contract and does not require plugin files.

## Verification

- The original CI run for PR head `42e82b2bfc570371d4fbc96198c8a3e5d2d41975` failed only during integration tests: 3 failed, 64 passed, 1 skipped.
- The failing engine error was `Tried to define variable '' but it does not start with $.` during card loading.
- The updated artifact has zero invalid `VAR` definitions; the old artifact had 227.
