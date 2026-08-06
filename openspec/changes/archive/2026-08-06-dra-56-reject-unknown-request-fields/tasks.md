# Tasks

Ordered so the decision is settled and the MCP cost measured before any schema is
touched — the option chosen depends on what `extra="forbid"` actually does to the
generated tool surface, which is not something to guess at.

## 1. Settle the decision

- [x] 1.1 Weigh `extra="forbid"`, the `ignored_fields` echo, and a capability
      endpoint against each other, and record the choice and the rejected
      alternatives in `design.md`.
- [x] 1.2 Establish which direction of skew each option covers, and state in
      `design.md` that the chosen option does **not** fix the deployment that
      produced DRA-53.
- [x] 1.3 Measure what `extra="forbid"` does to the generated MCP tool schema in
      this tree, rather than assuming it propagates. Record the result.
- [x] 1.4 Establish what FastMCP does with a tool argument that is not in the
      route's parameter map, since that decides whether the MCP surface can be
      protected at all.
- [x] 1.5 Survey the other services' request bodies and decide, per service, what
      is in scope and what is filed.

## 2. Prove the gap with a failing test

- [x] 2.1 Add a test asserting `PATCH /sessions/{id}` refuses an undefined field,
      and quote its failure against the unfixed tree.
- [x] 2.2 Add a test asserting `POST /sessions` refuses an undefined field.
- [x] 2.3 Add a test, derived from the app's own OpenAPI document, asserting every
      request body declares `additionalProperties: false` — so a model added later
      that forgets is a failure rather than a silent regression.

## 3. Make the request contract strict

- [x] 3.1 Add `StrictRequest` to `agent_orchestrator/schemas/base.py`, carrying
      `ConfigDict(extra="forbid")` and the reason it exists.
- [x] 3.2 Inherit it on every request model in `schemas/sessions.py`,
      `schemas/jobs.py`, `schemas/context.py`, `schemas/personas.py` and
      `schemas/players.py`, including the nested `PlayerReasoningConfig`.
- [x] 3.3 Give `POST /skills` a request model, keeping its `400` for a missing
      `name` so the endpoint's existing error contract is unchanged.
- [x] 3.4 Confirm `metadata`, `gateway_options` and `provider_options` still
      accept arbitrary contents.

## 4. Fix what the contract change breaks

- [x] 4.1 Run the unit and integration suites and enumerate every failure caused
      by a request body that now refuses a field.
- [x] 4.2 Fix each one at the caller, by sending what the endpoint defines —
      never by loosening the model back. **Nothing to fix: zero failures.** All
      691 pre-existing unit tests and all 31 integration tests pass untouched.
- [x] 4.3 Record how many tests changed and what each was sending. **None
      changed.** Record that as the finding it is — every caller in this
      repository was already keeping the contract, it simply was not checked.

## 5. Keep the documentation honest

- [x] 5.1 State the rule in `services/agent-orchestrator/README.md` and
      `services/agent-orchestrator/AGENTS.md`, including that a new request model
      inherits `StrictRequest`.
- [x] 5.2 Record in the MCP-surface documentation that the strictness does not
      reach a tool call, so nobody reads the OpenAPI schema and concludes it does.

## 6. Verify against a real server

- [x] 6.1 Run the orchestrator against a throwaway database, create a session,
      and confirm a `PATCH` with an undefined field is a `422` naming it while the
      same `PATCH` without it succeeds.
- [x] 6.2 Confirm the dashboard's own save path still succeeds end to end against
      that server.
- [x] 6.3 `./scripts/lint.sh --fix`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration`, `openspec validate --all`.

## 7. File what was deliberately left

- [x] 7.1 File the capability/version endpoint, naming it as the option that
      covers the direction this change cannot. — **DRA-59**
- [x] 7.2 File eval-service's `EvaluationRequestBody` and game-service's action
      models, and record which leniency is spec-required and must not be
      touched. — **DRA-60**
- [x] 7.3 File the MCP surface's own silent argument drop. — **DRA-61**
