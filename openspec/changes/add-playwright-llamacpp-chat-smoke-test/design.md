## Context

DragnCardsAI already has service-level end-to-end coverage for HTTP and MCP game lifecycle operations, but the highest-risk user path is still untested: a real user opening the dashboard, chatting with the orchestrator, and expecting that prompt to produce a real DragnCards game. That path crosses the Next.js dashboard, agent-orchestrator session and streaming APIs, provider configuration, game-service MCP assignment, and DragnCards room creation over Phoenix.

The repo also currently relies on configured hosted providers for realistic orchestration. That is useful for development, but it makes smoke coverage expensive, slower, and more brittle. A local `llama.cpp` server with a very small instruction model gives the project a cheap, deterministic-enough smoke path that can run entirely on a developer machine.

That browser smoke flow should be owned by a dedicated repo service rather than the dashboard package itself. The smoke runner has a different lifecycle, dependency set, and entrypoint than the Next.js app it drives.

## Goals / Non-Goals

**Goals:**
- Add a browser-driven smoke workflow that exercises the real dashboard Play chat flow.
- Run that smoke workflow against a local `llama.cpp` model endpoint instead of a hosted provider.
- Make the smoke workflow reliable enough to verify DragnCards game creation with bounded retries rather than one-shot timing assumptions.
- Keep the change aligned with existing provider, dashboard, and infrastructure contracts instead of adding a parallel test-only architecture.

**Non-Goals:**
- Guarantee perfect determinism for arbitrary prompts or full gameplay through the local model.
- Add broad browser coverage for all dashboard features.
- Replace the existing hosted-provider path for normal agent sessions.
- Modify the upstream DragnCards applications.

## Decisions

### D1: Treat the smoke flow as a `testing` capability change, not a new standalone capability

**Decision**: The browser smoke test will live under the existing `testing` capability, with delta specs in `testing/spec.md`, rather than creating a separate smoke-testing spec family.

**Alternatives considered**:
- *Create a new `chat-smoke-testing` capability*: Rejected because the behavior is test-layer coverage over existing services, not a new product capability.
- *Document it only in tasks*: Rejected because the smoke path changes testable system behavior and needs a durable spec contract.

**Rationale**: The smoke flow extends how the system is verified, not what end users can do beyond the existing dashboard and orchestrator contracts.

### D1a: Host the browser harness in a dedicated `services/smoketest` package

**Decision**: The Playwright config and browser smoke spec will live in `services/smoketest` instead of under `services/dashboard`.

**Alternatives considered**:
- *Keep Playwright inside the dashboard package*: Rejected because the smoke harness is test infrastructure, not dashboard runtime code, and it should be installable and runnable independently.
- *Place the harness under root-level scripts or a top-level test folder*: Rejected because the repo already organizes runnable units under `services/`, and the smoke flow benefits from a dedicated service-owned entrypoint.

**Rationale**: A standalone smoke-test service keeps the test harness isolated from the dashboard's app package while preserving a clear repo-local place for smoke-specific dependencies and execution.

### D2: Use a repo-local `llama.cpp` OpenAI-compatible server as the smoke-model runtime

**Decision**: The smoke path will target a small local model served by `llama.cpp` through its OpenAI-compatible HTTP interface, wired through the existing provider/model configuration path used by agent-orchestrator sessions.

**Alternatives considered**:
- *Use a hosted provider with a cheap small model*: Rejected because it adds secrets, cost, and external flakiness to the smoke path.
- *Mock the LLM response entirely*: Rejected because it would not validate the actual orchestrator prompt-execution path.
- *Add a bespoke fake provider inside agent-orchestrator*: Rejected because it creates a test-only branch that diverges from real runtime behavior.

**Rationale**: `llama.cpp` gives the project a local, OpenAI-shaped server that can exercise the real orchestration pipeline while staying cheap and self-contained.

### D3: Keep the browser flow black-box and verify success through DragnCards-visible state with retries

**Decision**: The Playwright smoke test will drive the dashboard as a user would, submit a prompt asking for game creation, wait for visible job completion, and then verify DragnCards-side game creation by polling the supported service-side state rather than asserting on transient UI text alone.

**Alternatives considered**:
- *Assert only that the chat transcript contains a success message*: Rejected because it can pass even if no game was actually created.
- *Inspect DragnCards frontend internals directly*: Rejected because that couples the test to upstream UI implementation we do not control.
- *Use a single immediate verification attempt*: Rejected because room creation and Phoenix state propagation are asynchronous.

**Rationale**: The smoke test must prove observable success across the service boundary. Retried verification handles eventual consistency in room creation and state refresh.

### D4: Add only minimal dashboard testability guarantees

**Decision**: The dashboard contract will guarantee only the selectors and visible workflow needed for this smoke path: create/select a session, submit a prompt, and observe that a job reached a terminal state.

**Alternatives considered**:
- *Add broad `data-testid` coverage for the whole dashboard*: Rejected because it expands surface area beyond the smoke need.
- *Rely only on text matching*: Rejected because text can be unstable as the UI evolves.

**Rationale**: A small, explicit automation contract is easier to preserve and avoids turning the UI into a test-selector matrix.

### D5: Separate smoke-runtime wiring from the normal dev stack

**Decision**: Infrastructure changes will define a documented smoke-test runtime path for `llama.cpp`, model file location, and env wiring without making the local smoke model a mandatory dependency for every normal `docker compose up` or service startup.

**Alternatives considered**:
- *Always start `llama.cpp` in the main stack*: Rejected because it imposes unnecessary resource usage on all developers.
- *Require each test to hand-roll the model startup command*: Rejected because it makes the smoke workflow harder to reproduce and support.

**Rationale**: The smoke path needs a standard entrypoint, but it should remain opt-in and lightweight.

## Risks / Trade-offs

- **[Risk] Small local models may ignore parts of the prompt and fail to call the right tools** → Mitigation: constrain the smoke prompt, assign only the needed MCPs/skills, and choose a model/configuration validated against this narrow workflow.
- **[Risk] DragnCards room creation and state refresh are asynchronous over Phoenix** → Mitigation: verify creation through bounded retries against observable session/game state instead of a single immediate assertion.
- **[Risk] Browser tests can become brittle if dashboard controls move or labels drift** → Mitigation: define a minimal stable automation contract for the Play workspace instead of relying on incidental markup.
- **[Risk] `llama.cpp` model startup and warm-up add local setup friction** → Mitigation: document the model/runtime contract clearly and keep it isolated to the smoke-test path.
- **[Risk] Upstream DragnCards behavior changes could delay or alter when room state becomes visible** → Mitigation: keep verification at the supported service boundary and tolerate bounded propagation delay rather than scraping upstream internals.

## Migration Plan

1. Add the smoke-model runtime wiring and documentation.
2. Add agent-orchestrator provider/session support for the smoke model path.
3. Add the dashboard automation contract needed by the browser test.
4. Add the `services/smoketest` Playwright harness and DragnCards creation verification with retries.
5. Validate the smoke path against the local stack before treating it as the supported workflow.

Rollback is straightforward: remove the smoke runtime wiring and Playwright smoke harness without impacting the existing hosted-provider or service-level test paths.

## Open Questions

- Which exact small model file should the repo standardize on for the smoke path, and will that model be downloaded on demand or managed outside the repo?
- Should the smoke runtime be started through Docker Compose, a repo script, or both?
- What is the most stable observable signal of “game created” for the retry loop: orchestrator events, game-service session state, or DragnCards HTTP room metadata?
