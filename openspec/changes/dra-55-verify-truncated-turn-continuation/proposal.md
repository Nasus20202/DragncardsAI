## Why

DRA-45's automatic continuation implementation is covered by unit tests, but its archived verification record leaves the running HTTP worker path and browser rendering unverified. The missing end-to-end evidence matters because the dashboard listens for named event types and renders transcript rows through a switch that can silently omit a newly added event. This change closes that verification gap with a fake-provider HTTP regression and a browser smoke scenario that exercises both the main Play transcript and the subagent output modal.

The context-guard call-site cleanup described in the archived DRA-45 design is already present on the merged branch (`estimate_request` is used by the continuation guard), so no behavioral production change is required for that item.

## What Changes

- Keep a deterministic fake-provider integration scenario at the agent-orchestrator HTTP API boundary that proves a truncated response is resumed, repeated truncation is capped, and the automatic-continuation kill switch completes without resuming.
- Add a Playwright smoke scenario in the dedicated `services/smoketest` package with controlled orchestrator responses, proving the `turn_continued` marker is visible between output segments in the Play transcript.
- Extend that browser scenario to open a subagent's output modal and prove the same continuation marker and output segments render there.
- Record the focused commands and their exact outcomes in the DRA-55 tasks artifact; do not claim live-provider or browser verification when dependencies are unavailable.

## Capabilities

### New Capabilities

None. This change adds regression and smoke coverage for behavior already specified and implemented by DRA-45; it does not introduce a new runtime capability.

### Modified Capabilities

None. The existing agent-orchestrator and dashboard requirements already describe automatic continuation and `turn_continued` rendering. This is a verification-only change, so the change opts out of spec deltas.

## Impact

- `services/agent-orchestrator/tests/integration/` gains focused API-boundary coverage using the existing in-process fake-provider harness.
- `services/smoketest/tests/` gains a deterministic browser scenario that intercepts orchestrator calls while driving the real dashboard surface.
- No production API, database schema, provider configuration, or runtime behavior changes are expected.
- The DRA-45 archived design's `estimate_request` note requires no source edit because the cleanup landed in commit `5dde8ef2`.
