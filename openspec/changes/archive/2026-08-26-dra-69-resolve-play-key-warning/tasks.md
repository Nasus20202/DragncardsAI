# Tasks

## 1. Stable Play row identities

- [x] 1.1 Carry source-event identities through every `AggEvent` produced by the
      Play event aggregator.
- [x] 1.2 Use the aggregated identities as React keys in the main transcript and
      subagent output modal.
- [x] 1.3 Preserve the earlier DRA-69 selector deduplication without changing
      shared selector files.

## 2. Regression coverage

- [x] 2.1 Cover distinct same-content rows and stable identities when later events
      are appended.
- [x] 2.2 Capture React console errors while rendering repeated row content and
      assert that no duplicate-key warning is emitted.

## 3. Verification and delivery

- [x] 3.1 Run the focused Play dashboard Vitest files.
- [x] 3.2 Run the dashboard TypeScript check.
- [x] 3.3 Commit the finished implementation on the DRA-69 follow-up branch.
