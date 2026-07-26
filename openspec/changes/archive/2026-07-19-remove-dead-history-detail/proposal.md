## Why

The play-style history browser reimplemented per-event detail rendering (agent, user, and game-service details, score rows, and value formatting) inline inside `history-transcript.tsx`. The earlier standalone `history-detail.tsx` component was left behind: nothing imports it — the `history-detail-agent`/`-game`/`-user` occurrences in the transcript and tests are `data-testid` string literals, not imports of the module. It is confirmed dead code carrying ~300 lines plus a 127-line test that only exercises the orphaned component.

## What Changes

- **dashboard** removes the dead `features/history/components/history-detail.tsx` component (exports `HistoryDetail` and helpers `Field`, `stringifyValue`, `formatScore`, `AgentDetail`, `UserDetail`, `GameServiceDetail`, `EvaluatorDetail`, `ScoreRow`, `CRITERIA`) and its sole test `features/history/__tests__/history-detail.test.tsx`.
- No behavior change: readable per-event detail rendering already lives inline in `history-transcript.tsx`; the live copies of any duplicated helpers (in `history-rounds.ts` / `history-transcript.tsx`) are untouched.

## Impact

- dashboard only; no backend, endpoint, or spec-behavior changes. Cleanup of unreferenced code and its dead test. All transcript testids and behaviors are preserved.
