# Tasks

## 1. Poll context usage during active generation

- [x] 1.1 Add a Play context metadata polling hook with immediate active refresh, settled self-scheduling polls, latest callback handling, and timer cleanup on inactive/session-change/unmount.
- [x] 1.2 Integrate the polling hook with `usePlaySession` using the existing `streamingJobId` generation state and serialize same-session context refresh triggers.

## 2. Regression coverage

- [x] 2.1 Add focused fake-timer hook tests for active polling, delayed requests without overlap, transition to inactive, dependency changes, and unmount cleanup.
- [x] 2.2 Run the focused dashboard polling test and record the result; do not run the full dashboard suite or browser verification.

## 3. Complete the specification

- [x] 3.1 Validate the completed OpenSpec change and confirm no placeholder content remains.
