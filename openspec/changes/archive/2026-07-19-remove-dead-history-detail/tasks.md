## 1. Remove dead component

- [x] 1.1 Verify no import of the `HistoryDetail` component or the `history-detail` module anywhere in the dashboard (data-testid string literals in `history-transcript.tsx` and tests are not imports and stay).
- [x] 1.2 Delete `services/dashboard/features/history/components/history-detail.tsx`.
- [x] 1.3 Delete its sole test `services/dashboard/features/history/__tests__/history-detail.test.tsx`.

## 2. Verify no regressions

- [x] 2.1 Typecheck passes: `pnpm exec tsc --noEmit`.
- [x] 2.2 Dashboard tests pass: `pnpm vitest run`.
- [x] 2.3 Lint passes: `./scripts/lint.sh --fix`.
