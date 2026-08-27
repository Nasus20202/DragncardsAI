## 1. Safe child launch

- [x] 1.1 Propagate a failed persistent seat claim through the shared child launcher, terminate the losing session, and return an error before configuration or enqueue; verify with the focused seat-session tests.

## 2. Regression coverage

- [x] 2.1 Add a prompt-player handler regression proving a failed claim schedules no child job, terminates the losing session, and leaves the persisted owner unchanged; verify with the focused seat-session test module.

## 3. Verification

- [x] 3.1 Run formatting, focused orchestrator tests, OpenSpec validation, and the repository-required full checks; record observed results before archive.
