# Stop the dashboard suite from racing the render it is asserting on

## Why

DRA-50 reports `features/play/__tests__/play-workspace-execution.test.tsx >
"submits a prompt and refreshes the job list"` failing intermittently with

```
Unable to find an accessible element with the role "status"
```

It was seen on 2026-08-05 as 637/637 on one run and 636/637 on the very next run
of an unchanged tree, passing 3/3 in isolation, while several worktrees were
running suites on the same machine. Nothing in the change being verified touched
dashboard source, so the defect is in the test, not in the workspace.

The test waits for the wrong event. It awaits

```ts
await waitFor(() => expect(api.submitPrompt).toHaveBeenCalledWith(...));
```

and then queries the streaming banner **synchronously**. But `submitPrompt`
having been *called* is the first step of `submitSessionPrompt`, not the last:
the handler awaits `submitPrompt`, then awaits `getJob`, and only then calls
`startStreaming`, which is what sets `streamState` to `"streaming"` and renders
the `role="status"` banner. Between the awaited condition and the assertion sit
two further promise resolutions and a React commit.

Nothing waits for that commit. React Testing Library's `asyncWrapper` turns the
act environment **off** for the duration of `waitFor`, so the submit chain's state
updates are scheduled the way the browser would schedule them, and then gives them
exactly one `setTimeout(…, 0)` — clamped to a single millisecond — to land before
handing control back to the test. That is a fixed grace period, not a wait for the
condition. Whether the chain fits inside it is a property of the machine, not of
the behaviour under test: an extra task anywhere in the chain, a garbage
collection pause, or another suite competing for the same cores pushes the commit
past the window, the assertion runs against a DOM that has not updated, and
`getByRole` throws. The suite is asserting on a render it never agreed to wait
for.

This was confirmed directly rather than inferred. Holding the test otherwise
unchanged and resolving `getJob` one macrotask later — the delay a contended
machine imposes on that chain — makes the synchronous query fail with exactly the
reported error, repeatably, while the same test with an awaited query passes under
the identical condition. The scheduling that decides the window is itself unstable
here: the same probe comparing that `setTimeout(0)` against a `MessageChannel`
task reported each ordering on different runs of the same code.

The failure was **not** reproduced by load alone, and the record should say so
plainly. Roughly 1,400 executions of the scenario — 100 consecutive runs of the
file against two looping suites, 27 runs pinned to a contended single core, eight
concurrent full suites above a load average of 120, and an in-process probe
repeating the scenario and counting — produced no miss. That is consistent with
the one occurrence reported out of a full run; it puts the natural rate well below
one in a thousand, and it is why the diagnosis rests on the deterministic
condition above rather than on a lucky failure.

The component is fine. `streamState` becomes `"streaming"` on every path through
`startStreaming`, and `setStreamingJobId` and `setStreamState` are set together,
so the banner and the active job id land in one commit. There is no ordering in
which the banner fails to appear; there is only an ordering in which the test
looks too early.

## What Changes

### The assertion waits for the banner instead of racing it

The streaming banner is asserted with an awaited `findByRole`, so the test waits
for the render that produces it rather than for an earlier step that merely
precedes it. The assertions that follow stay synchronous: they read state
committed in the same render, so once the banner is on screen they cannot be
early.

### Nothing else in the suite shares the defect

Every `await waitFor(...)` in the dashboard suite whose awaited condition is a
mock call rather than a DOM state was reviewed for the same shape — seventeen
occurrences, of which this is the one defect. The rest either follow it with
another `await waitFor`, assert an *absence*, assert a value that was already on
screen before the awaited call and is asserted to be unchanged, or assert content
the component renders from its props before that call resolves — none of which can
fail by being early. They are listed in the tasks so the review is on the record
rather than implied.

## Capabilities

### Modified Capabilities

- `testing` — the dashboard suite's result is required to be independent of the
  machine's load, and asynchronously rendered content must be asserted with
  awaited queries.

## Impact

- **dashboard** — `features/play/__tests__/play-workspace-execution.test.tsx`
  only. One assertion changes from `getByRole` to `await findByRole`.
- **No source change.** No component, hook, or helper is touched; the workspace
  behaves exactly as before.
- **No change to test counts.** 721 dashboard tests before and after.

## Non-goals

- **No lint rule.** An ESLint rule banning synchronous queries after an awaited
  `waitFor` cannot tell the safe uses from the unsafe one — most of the suite's
  occurrences are correct, and `eslint-plugin-testing-library`'s nearest rules
  (`await-async-queries`, `prefer-find-by`) do not describe this shape at all. A
  rule that fires on the safe majority would be turned off or worked around
  within a week. The requirement stated here is the durable form of it.
- **No shared test helper.** The fix is choosing the right query, not wrapping
  one; a helper would add indirection without removing the decision.
- **No rewrite of the surrounding tests.** The other tests in the file already
  await what they assert on, and churning them would obscure the one-line fix.
- **No change to the streaming banner or any other component.** The design is the
  owner's reference and this is a test correction.
