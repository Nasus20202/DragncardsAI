## Context

See `proposal.md` for the motivation. DRA-45 already owns the runtime behavior and the dashboard row. The merged branch has an agent-orchestrator integration fixture (`FakeBifrost`/`TruncatingBifrost`) that drives the real FastAPI application and worker through `httpx.ASGITransport`, while `services/smoketest` is the repository's supported Playwright runner for the real dashboard surface.

The verification must be deterministic and must not spend hosted-provider tokens. The HTTP harness therefore substitutes the Bifrost client at application construction time. The browser harness substitutes only orchestrator HTTP responses with Playwright routing; it still loads and interacts with the dashboard's built page, including the actual transcript and modal components.

## Goals / Non-Goals

**Goals:**

- Prove through the service HTTP boundary that a truncating response resumes, the configured continuation cap stops repeated truncation, and the kill switch preserves the pre-DRA-45 completion behavior.
- Prove in a real Chromium page that the continuation seam is visible in the main Play transcript and in a subagent output modal.
- Keep all evidence local, repeatable, and independent of ambient provider credentials.
- Record whether live-stack prerequisites were available without disguising a skipped runtime check as a pass.

**Non-Goals:**

- Change production continuation, transcript aggregation, or rendering behavior.
- Add a new provider, API endpoint, database migration, or dashboard abstraction.
- Replace the existing local llama.cpp end-to-end smoke test, which remains responsible for live game creation.
- Rework DRA-45's context guard: the merged code already uses `estimate_request`, as requested by the archived rebase note.

## Decisions

### Use the existing in-process HTTP harness for fake-provider worker coverage

The integration app is created with the production FastAPI app factory, repository, worker lifecycle, and HTTP routers, but receives a deterministic fake Bifrost. Extend the existing truncating fake to accept response sequences and allow test-only settings overrides. Add separate focused scenarios for a one-continuation cap and for `auto_continue_truncated_turns=False`; assert job status/result and the persisted event sequence while ignoring non-contractual progress events.

**Alternatives considered:** pointing a live Bifrost container at a temporary HTTP server, or adding a new provider implementation. Both introduce network timing, process cleanup, and provider-schema behavior unrelated to this contract; they would make a regression test less deterministic without exercising more of the worker than the existing app-boundary harness.

### Use Playwright route interception for dashboard rendering

Add one test under `services/smoketest/tests` that serves a completed parent job containing a continuation seam and a completed child job containing its own seam. Route the dashboard's orchestrator requests to these fixtures, load `/play`, assert the parent marker and output, expand the subagent list, open the child output modal, and assert the child marker and output there. This directly guards the silent switch omission described in the issue while avoiding a model call for a rendering-only check.

**Alternatives considered:** adding another jsdom/RTL unit test, or driving the local llama.cpp model and trying to force a truncation through model configuration. The existing dashboard unit test already covers the static aggregation contract, while jsdom cannot prove the built browser event/render path. The local model is not a controllable fake provider and cannot reliably produce a provider `finish_reason: "length"`, so it cannot defend this exact boundary.

### Keep the verification-only OpenSpec without a spec delta

The existing `agent-orchestrator` and `dashboard` specs already describe the runtime continuation and `turn_continued` rendering requirements. This change adds only regression evidence, so `.openspec.yaml` sets `skip_specs: true`; the proposal, design, and tasks remain the durable record of what was exercised and what could not be exercised.

**Alternatives considered:** duplicating existing runtime requirements in a new delta spec. That would create a second contract for unchanged behavior and make future drift more likely.

## Risks / Trade-offs

- The fake-provider HTTP scenario does not prove Docker networking or a deployed Bifrost instance; it intentionally proves the worker and API contract without external nondeterminism. A live-stack run is recorded separately when the stack and submodules are available.
- The browser scenario proves the dashboard's rendered DOM with controlled API data, not a real provider-to-browser stream. The existing live smoke test remains the place for cross-service llama.cpp and game creation behavior.
- Dashboard route fixtures can become stale if the API response shape changes. Keeping them in the dedicated smoke package and using the same endpoint paths as `client-api.ts` makes an unhandled request fail the test instead of silently weakening it.
- No DragnCards WebSocket behavior is changed or mocked by this change. The smoke scenarios do not exercise upstream room protocol; the real game-creation smoke remains the guard for that integration.
