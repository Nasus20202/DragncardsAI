## 1. DragnCards action translation

- [x] 1.1 Add an inline DragnLang cleanup operation to the typed `VillainEndPhaseAction` translation, filtering authoritative boost-marked engine cards, clearing transient state, moving them to `sharedEncounterDiscard`, skipping an already-discarded card's move, and preserving the existing `villainEndPhase` action; verify the generated payload remains DragnCards-only and contains no identity-logging operation.
- [x] 1.2 Add focused translation regression tests for the draw-boost/villain-end sequence, asserting cleanup is selected by the `boost` marker rather than a hidden entry or stack position and that the existing phase action remains last; verify the targeted action translation test file passes.

## 2. Privacy and platform regression coverage

- [x] 2.1 Add a DragnCards normalization regression fixture for a rotated boost encounter card, asserting the caller receives only the merged `HIDDEN` count and no card identity while authoritative metadata remains available to the engine-side action; verify the targeted state test passes.
- [x] 2.2 Extend existing Marvel LCG visibility-matrix coverage to assert owner hand ACL disclosure and non-owner/spectator redaction remain unchanged after the DragnCards cleanup translation; verify the targeted Marvel state tests pass.

## 3. OpenSpec completion

- [x] 3.1 Validate the complete change artifacts and ensure every task is checked only after implementation and focused tests provide evidence; verify `openspec validate --change dra-92-dragncards-hidden-card` reports no errors.
