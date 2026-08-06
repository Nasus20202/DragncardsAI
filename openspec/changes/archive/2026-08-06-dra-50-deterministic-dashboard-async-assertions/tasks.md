# Tasks

Ordered so the failure is established and explained before anything is changed —
a flake fixed without being seen fail is a guess.

## 1. Establish the failure

- [x] 1.1 Run the file in isolation and confirm it passes, so the defect is not
      an unconditional one.
- [x] 1.2 Try to reproduce it under load and record honestly what that did and did
      not produce. It did **not** reproduce: 100 consecutive runs of the file
      while two other full dashboard suites looped on the same machine; 27 runs
      pinned to a single core against 3 and then 10 competing busy loops; 8
      concurrent full-suite runs at a load average above 120; and an in-process
      probe repeating the exact scenario, which found the banner present at the
      moment the test looks in every one of roughly 1,400 executions. The natural
      rate is evidently well below one in a thousand, which is consistent with the
      single occurrence reported.
- [x] 1.3 Reproduce the reported error deterministically instead: hold the test
      unchanged and resolve `getJob` one macrotask later — the delay a contended
      machine imposes on the submit chain — and confirm the error matches the
      report, `Unable to find an accessible element with the role "status"`,
      raised from the `getByRole` line.
- [x] 1.4 Confirm the same test with an awaited query passes under that identical
      condition, so the difference is the query and nothing else.
- [x] 1.5 Confirm the grace period the assertion depends on is genuinely unstable
      here: a probe comparing Testing Library's `setTimeout(…, 0)` drain against a
      `MessageChannel` task reported each ordering on different runs of the same
      code.

## 2. Explain it

- [x] 2.1 Read `submitSessionPrompt` and confirm `submitPrompt` being called is
      separated from `startStreaming` by two further awaits.
- [x] 2.2 Confirm `startStreaming` sets `streamState` to `"streaming"` on every
      path, so no ordering exists in which the banner fails to render — the defect
      is in the test, not the component.
- [x] 2.3 Confirm React Testing Library's `asyncWrapper` disables the act
      environment for `waitFor` and drains with a single `setTimeout(…, 0)`, which
      is what makes the outcome depend on the machine.
- [x] 2.4 Confirm `setStreamingJobId` and `setStreamState` are set together and so
      commit in one render, which is why the assertions after the banner can stay
      synchronous.

## 3. Fix it

- [x] 3.1 Assert the streaming banner with `await screen.findByRole("status", …)`
      in `"submits a prompt and refreshes the job list"`.
- [x] 3.2 Leave the following assertions synchronous — same commit, so they cannot
      be early — rather than converting the whole test to awaited queries.

## 4. Check the rest of the suite for the same habit

- [x] 4.1 Sweep every `await waitFor(...)` in `services/dashboard/features` whose
      awaited condition is a mock call rather than DOM state, and classify what
      follows it. Seventeen occurrences; one is the defect.
- [x] 4.2 Record the ones deliberately left alone and why: those followed by a
      further `await waitFor` (`play-workspace-removal` ×2,
      `play-workspace-skill-attachment` ×3, `history-games-picker`,
      `persona-editor`); those asserting an absence, which cannot fail by being
      early (`evaluation-control`, `play-config-panel-persona` ×2, `seat-roster`);
      those asserting a value that was already on screen before the awaited call
      and is asserted unchanged, where an early read gives the same answer
      (`play-workspace-configuration`, `use-history`, `history-transfer`); and
      `seat-roster` ×2, whose rows are derived from the `players` prop and are
      rendered before `listPersonas` resolves.
- [x] 4.3 Confirm no other test in the suite queries synchronously for content
      that only a later render produces. The streaming banner is the suite's only
      `role="status"` query at all.

## 5. Verify

- [x] 5.1 Run the fixed file 120 consecutive times while two other full dashboard
      suites loop on the same machine, and record the count.
- [x] 5.2 Re-run the deterministic delayed-`getJob` condition against the awaited
      assertion and confirm it passes.
- [x] 5.3 `./scripts/lint.sh --fix`, `pnpm typecheck` in `services/dashboard`,
      `./scripts/test.sh unit`, `openspec validate --all`.
- [x] 5.4 Confirm the dashboard suite still reports 721 tests, since no test is
      added or removed.
