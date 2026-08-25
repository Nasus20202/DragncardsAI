# Tasks

## 1. Marvel driver setup integrity

- [x] 1.1 Retain setup witnesses from the selected scenario and ordered hero documents at table creation
- [x] 1.2 Validate player count, ordered hero identities, villain, and main scheme in the first ready world
- [x] 1.3 Fail with a descriptive setup-integrity error and let session creation tear down the driver
- [x] 1.4 Add unit coverage for matching and mismatched selected setup worlds

## 2. Render acknowledgement liveness

- [x] 2.1 Add per-seat bounded acknowledgement retry and serialization
- [x] 2.2 Mark acknowledgement exhaustion as explicit transport degradation
- [x] 2.3 Acknowledge and consume empty-pending reveal frames before waiting for a real pending seat
- [x] 2.4 Preserve the no-invented-options behavior for empty pending seats
- [x] 2.5 Add unit coverage for empty-reveal advancement and bounded acknowledgement failure

## 3. Repository-controlled engine hardening

- [x] 3.1 Add an exact Docker patch overlay disabling the hardcoded startup-save fallback
- [x] 3.2 Apply the overlay with zero fuzz in the repository-owned Marvel image
- [x] 3.3 Pin the overlay behavior in a focused infrastructure test or static assertion

## 4. Verification and delivery

- [x] 4.1 Run focused game-service Marvel unit tests
- [x] 4.2 Run focused Marvel integration coverage when the engine is available
- [x] 4.3 Run OpenSpec validation, archive the change, and verify the archived path
- [x] 4.4 Commit the implementation on the DRA-72 branch without touching DRA-70 or DRA-71 files
