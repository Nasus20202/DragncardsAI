## 1. Build fixes

- [x] 1.1 Replace the deprecated naive session timestamp factory with an aware UTC factory.
- [x] 1.2 Pin the Marvel Champions plugin submodule to the last known compatible revision.

## 2. Regression coverage

- [x] 2.1 Assert default `GameSession` timestamps are timezone-aware UTC values.
- [x] 2.2 Assert plugin automation `VAR` definitions have valid names in the integration suite.
- [x] 2.3 Run focused local checks and verify the pushed pull-request build.
