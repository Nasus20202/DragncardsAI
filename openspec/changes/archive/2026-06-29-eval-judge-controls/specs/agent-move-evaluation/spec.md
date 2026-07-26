## ADDED Requirements

### Requirement: Per-evaluation judge configuration

The eval-service SHALL accept an optional per-evaluation `judge` configuration — provider, model, reasoning effort, a custom prompt/rubric, and a set of rules-skill names — that overrides the server defaults for that evaluation only, and SHALL record the model and provider actually used on each verdict's evaluator metadata. Selected skill names SHALL be resolved to skill content and supplied to the judge; an unknown skill name SHALL be rejected.

#### Scenario: Request overrides the judge model and skills

- WHEN an evaluation request supplies a `judge` object with a `model_name`, `reasoning` effort, and a list of valid `skills`
- THEN the eval-service evaluates the selected targets with that model and reasoning, includes the named skills' content in the judge prompt, and records the used model/provider on the resulting verdict

#### Scenario: Omitted judge config falls back to server defaults

- WHEN an evaluation request omits the `judge` object or individual fields
- THEN the eval-service uses the configured default judge model/provider/reasoning for the missing fields

#### Scenario: Unknown skill is rejected

- WHEN an evaluation request names a skill that does not exist under the configured skill roots
- THEN the eval-service rejects the request with a client error and does not start any evaluation

### Requirement: Streaming evaluation progress

The eval-service SHALL expose a Server-Sent Events stream for an evaluation request that emits per-target status transitions, incremental judge output, completed verdicts, and a terminal completion event.

#### Scenario: Client streams status and verdict

- WHEN a client connects to the evaluation request's SSE stream while targets are processing
- THEN it receives an initial status snapshot, status events on each target transition, incremental judge output events, a verdict event when a target completes, and a final done event before the stream closes

### Requirement: Cancellable evaluation

The eval-service SHALL support cancelling an evaluation request, marking all non-terminal targets as `cancelled`, aborting any in-flight judge call, and writing no verdict for cancelled targets. `cancelled` SHALL be a terminal target state reflected in the request-status aggregate.

#### Scenario: Cancel an in-flight evaluation

- WHEN a cancel request is issued for an evaluation request that has pending or running targets
- THEN those targets transition to `cancelled`, any in-flight judge call is aborted, no verdict is written for them, and the stream reports the cancellation and closes

#### Scenario: Cancel a finished request is a no-op

- WHEN a cancel request is issued for an evaluation request whose targets are all terminal
- THEN the eval-service makes no changes and reports zero cancelled targets
