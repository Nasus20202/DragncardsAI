## 1. Extract shared CollapsibleCard

- [x] 1.1 Add `features/shared/components/collapsible-card.tsx` reconciling the Play (timestamped) and History (testId/break-words) variants via props.
- [x] 1.2 Update `features/play/components/play-event-card.tsx` to delegate to the shared component.
- [x] 1.3 Update `features/history/components/conversation-transcript.tsx` to import the shared component and pass `breakBody`/`testId`.

## 2. Extract shared RightDrawer

- [x] 2.1 Add `features/shared/components/right-drawer.tsx` (backdrop + outside-click close + right `aside`, parametrized `ariaLabel`/`testId`/`maxWidthClass`).
- [x] 2.2 Update `features/history/components/evaluation-queue.tsx` to use `RightDrawer`.
- [x] 2.3 Update `features/history/components/history-scorecard.tsx` to use `RightDrawer` (`max-w-lg`).
- [x] 2.4 Update the Evaluate drawer in `features/history/components/history-workspace.tsx` to use `RightDrawer`.

## 3. useScrollLock

- [x] 3.1 Investigated: no duplicated dynamic body-scroll locking exists (only static `overflow-hidden` on `<body>`). Extraction not warranted.

## 4. Verify no regressions

- [x] 4.1 Typecheck passes: `pnpm exec tsc --noEmit`.
- [x] 4.2 Dashboard tests pass: `pnpm test`.
- [x] 4.3 Lint passes: `./scripts/lint.sh --fix`.
