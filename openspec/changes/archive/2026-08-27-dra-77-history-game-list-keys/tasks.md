## 1. Platform-qualified History identity

- [x] 1.1 Add normalized `(game_id, platform)` History identity helpers and use them for list keys, active rows, callbacks, delete targets, refresh retention, and optional deep links; verify legacy DragnCards records retain their existing behavior.
- [x] 1.2 Propagate the selected platform through timeline, snapshots, restore, reconstruction lifecycle, export, and evaluation/round requests; verify Marvel rows cannot operate on a same-id DragnCards partition.
- [x] 1.3 Return an imported bundle's platform and reselect that exact History partition; verify a Marvel import cannot select a same-id DragnCards record.

## 2. Regression coverage

- [x] 2.1 Extend History picker coverage with two platform records sharing one game id; verify both rows render without React key warnings, select independently, and delete their own platform partition.
- [x] 2.2 Cover an explicit Marvel deep link and platform-qualified timeline/evaluation requests; verify legacy `game_id` navigation still defaults to DragnCards.
- [x] 2.3 Cover the import response platform through the history-service API and dashboard transfer callback.

## 3. Validation

- [x] 3.1 Run the focused dashboard test, dashboard typecheck/lint, and `openspec validate --all`; verify all checks pass.
