## 1. Evaluator context isolation

- [x] 1.1 Add an optional player constraint to neighbouring-move selection and pass the attributed target player through move assembly; verify with a regression test containing interleaved player1 and player2 moves.
- [x] 1.2 Run the eval-service assembly and rounds unit tests; verify unattributed chat moves retain aggregate neighbouring context.

## 2. History attribution

- [x] 2.1 Render a compact player label for attributed agent moves and omit it for legacy unattributed moves; verify with the History transcript component test.
- [x] 2.2 Run the dashboard History transcript test file and verify both player labels are visible in the rendered timeline.

## 3. Integration verification

- [x] 3.1 Run the repository lint, unit, integration, and OpenSpec validation commands; verify no existing contract regresses.
