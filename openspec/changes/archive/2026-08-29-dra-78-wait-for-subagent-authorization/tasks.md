## 1. Wait authorization boundary

- [x] 1.1 Add a pre-resolution ownership check to `wait_for_subagent` that requires the requested job's persisted parent to match the current parent and the current parent job's session to match the bound orchestrator session, rejecting missing context or mismatches without invoking child polling.
- [x] 1.2 Preserve the existing authorized-child outcome path, including result wrapping, absolute timeout handling, parent cancellation, and timeout event recording.

## 2. Regression coverage

- [x] 2.1 Update direct wait tests to construct and bind owned parent/child jobs, proving successful terminal results remain available under the authorization contract.
- [x] 2.2 Add focused tests for foreign-parent and foreign-session jobs that assert generic errors, no live-bus subscription/polling, and no result disclosure.
- [x] 2.3 Keep timeout and cancellation tests exercising authorized children and assert their existing outcomes remain unchanged.

## 3. Verification

- [x] 3.1 Run the focused agent-orchestrator wait and subagent regression tests and validate the completed OpenSpec change.
