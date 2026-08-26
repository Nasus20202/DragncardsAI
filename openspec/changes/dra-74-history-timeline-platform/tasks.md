# Tasks

## 1. Platform-aware history API

- [x] 1.1 Add optional platform handling to paged events and timeline reads
- [x] 1.2 Carry the platform through complete-event detail, cursor pagination, and snapshots
- [x] 1.3 Include the selected platform on history export URLs
- [x] 1.4 Preserve the DragnCards compatibility default when no platform is reported

## 2. Dashboard history state

- [x] 2.1 Resolve the selected game's platform with the DragnCards fallback in the workspace
- [x] 2.2 Pass the resolved platform through initial loads, incremental refreshes, and detail fetches
- [x] 2.3 Keep the selected platform aligned across transcript, export, board, and deletion controls

## 3. Regression coverage

- [x] 3.1 Add focused Marvel URL-query assertions for history API reads
- [x] 3.2 Add hook coverage for Marvel timeline and snapshot partition selection
- [x] 3.3 Add workspace coverage for a Marvel game with recorded events rendering a nonempty transcript
- [x] 3.4 Update existing detail-read expectations for the explicit legacy platform fallback

## 4. Delivery

- [x] 4.1 Write the complete DRA-74 OpenSpec proposal, design, tasks, and specification delta
- [x] 4.2 Run the focused dashboard test suite and dashboard TypeScript typecheck
- [x] 4.3 Commit the coherent implementation and OpenSpec change on the DRA-74 branch
