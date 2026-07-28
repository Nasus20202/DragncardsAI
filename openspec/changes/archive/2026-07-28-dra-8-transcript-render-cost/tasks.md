# Tasks

## 1. Measure before optimising

- [x] 1.1 Benchmark the Play transcript's mount time, mounted element count and
      per-streamed-token re-render time across realistic shapes (1 job with
      48/500/1000 events; 3, 6 and 10 jobs up to 3000 events), appending tokens
      exactly the way `applyStreamEventToJob` does.
- [x] 1.2 Benchmark the History transcript's mount time, selection-change time and
      search-keystroke time at 100, 300, 900 and 2000 events.
- [x] 1.3 Measure the real browser against the live backends: mounted element count
      and content height for a real 485-event session, and scroll frame timing
      across that transcript and across a six-times-larger one, to decide whether
      the mounted node count justifies windowing.

## 2. Play transcript

- [x] 2.1 Memoise `ReasoningBlock`, `CompactionBlock`, `ModelOutputBlock` and
      `CollapsibleEventBlock`. All take primitives or a `JobEventResponse` whose
      identity `upsertStreamEvent` preserves unless the payload changed, so the
      default shallow comparison is correct.
- [x] 2.2 Memoise `JobThread` and move its `aggregateEvents` call into a `useMemo`
      keyed on the job's event list.
- [x] 2.3 Confirm the existing follow-lock suite still passes unchanged.

## 3. History transcript

- [x] 3.1 Memoise `TranscriptEvent`.
- [x] 3.2 Replace the per-row `selectedSeq` prop with a `selectedVerdictSeq` that is
      non-null only when the selection is one of that row's verdicts, so moving the
      selection does not change a prop on every row.
- [x] 3.3 Share one empty verdict list instead of a fresh `[]` per ungraded row, and
      hoist the default expand and reveal pulses out of the parameter defaults.
- [x] 3.4 Stabilise the props the workspace hands to every row: `useCallback` the
      restore handler and `useMemo` the board-action bundle.

## 4. Regression guard and verification

- [x] 4.1 Add a Play test that counts markdown renders and asserts one streamed
      token re-renders only the response it changed, and that an unchanged job list
      re-renders nothing.
- [x] 4.2 Add a History test that counts row renders and asserts a selection change
      touches only the rows gaining and losing the selection.
- [x] 4.3 Verify both guards fail against the unmemoised components.
- [x] 4.4 Verify in the browser against the live backends that the transcript's
      rendered DOM and pixels are unchanged, and that every follow-lock behaviour
      still holds: default following, wheel/key/touch release, no viewport yank
      while streaming and scrolled up, re-engage on return to the bottom, the
      re-engage control appearing and disappearing at the right times, and the
      content-resize cases.
