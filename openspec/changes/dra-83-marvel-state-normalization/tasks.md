## 1. Marvel normalizer contract

- [x] 1.1 Normalize Marvel descriptor info into the neutral sparse token names, including current scheme threat and Crisis, Hazard, and acceleration indicators; preserve public metadata needed by existing consumers. Verify with direct normalizer assertions.
- [x] 1.2 Derive `villainHitPoints` only from an authoritative visible active villain health value and omit it when unavailable; verify both real and absent health cases.
- [x] 1.3 Map active `area_schemes_side` cards to `sharedSideSchemes` using the existing visibility and hidden-card rules. Verify named Crowd Control, Breakin' & Takin', and Highway Robbery entries.
- [x] 1.4 Classify all current Marvel engine phase labels, including Enemy Activation, without changing the opaque phase label. Verify valid phase table and unknown fallback.

## 2. Neutral schema and regression fixture

- [x] 2.1 Make the neutral villain HP field optional so absent Marvel facts remain absent while existing DragnCards values remain compatible. Verify model serialization omits the field when unset.
- [x] 2.2 Add a deterministic recorded-Rhino-shaped fixture covering 9/14, 12/14, and 14/14 main-scheme checkpoints, Rhino I at 19 HP, and active side-scheme effects. Verify the fixture is consumed by focused unit tests.

## 3. Completion proof

- [x] 3.1 Run the focused Marvel game-service unit tests and OpenSpec validation; record exact commands and results.
