## ADDED Requirements

### Requirement: A subagent run is bounded by a timeout
A subagent job SHALL be bounded by an absolute timeout (`SUBAGENT_TIMEOUT_SECONDS`, default 30 minutes, must be positive) measured from the start of its run. When the run has not reached a terminal event within that budget, the worker SHALL stop the run and mark the job failed with error code `subagent_timeout`, non-retryable, and SHALL terminate the child session. The timeout SHALL bound the model call itself, so a provider call that hangs past the budget is cancelled rather than holding the worker. Top-level jobs SHALL NOT be subject to the timeout.

#### Scenario: A hanging provider call times the subagent out
- **WHEN** a subagent's provider call does not return before `SUBAGENT_TIMEOUT_SECONDS` elapses
- **THEN** the worker SHALL cancel the call
- **AND** SHALL mark the subagent job failed with error code `subagent_timeout`
- **AND** SHALL record a `failure` event carrying that error code
- **AND** SHALL terminate the subagent's child session

#### Scenario: A subagent run that keeps working is not timed out
- **WHEN** a subagent produces tool calls or content within `SUBAGENT_TIMEOUT_SECONDS` of its previous activity
- **THEN** the run SHALL continue without the timeout firing

#### Scenario: Top-level jobs are not timed out
- **WHEN** a top-level job (no parent job) runs longer than `SUBAGENT_TIMEOUT_SECONDS`
- **THEN** the timeout SHALL NOT apply to that job

### Requirement: A subagent fails after three consecutive identical model-call errors
When a subagent's model call fails, the worker SHALL count the failure by its error code instead of ending the run on the first failure. Three consecutive calls failing with the same error code SHALL mark the job failed with error code `subagent_error_loop`, non-retryable, and SHALL terminate the child session. A call that succeeds, or a failure with a different error code, SHALL reset the streak. The failure message SHALL name the repeated error code so the underlying cause stays diagnosable. Top-level jobs SHALL keep their existing single-failure behaviour.

#### Scenario: The same transport error repeats three times
- **WHEN** a subagent's model call raises the same error code on three consecutive calls
- **THEN** the worker SHALL mark the subagent job failed with error code `subagent_error_loop`
- **AND** SHALL record a `failure` event carrying that error code and the repeated code
- **AND** SHALL terminate the subagent's child session

#### Scenario: A different error code resets the streak
- **WHEN** a subagent's model call fails with a different error code than the previous failure
- **THEN** the streak SHALL restart at one
- **AND** the run SHALL continue

#### Scenario: A successful call resets the streak
- **WHEN** a subagent's model call succeeds after one or two failures
- **THEN** the error streak SHALL be reset
- **AND** the run SHALL continue

### Requirement: A subagent fails after three consecutive empty responses
A subagent response with neither tool calls nor content SHALL NOT complete the run. Three consecutive such responses SHALL mark the job failed with error code `subagent_no_progress`, non-retryable, and SHALL terminate the child session. A response carrying content or tool calls SHALL reset the streak and complete the run as usual. A response truncated at the provider's output cap SHALL be handled by the truncation continuation machinery, not by this check. Top-level jobs SHALL keep their existing behaviour.

#### Scenario: Three empty responses in a row fail the subagent
- **WHEN** a subagent returns a response with no tool calls and no content on three consecutive model calls
- **THEN** the worker SHALL mark the subagent job failed with error code `subagent_no_progress`
- **AND** SHALL record a `failure` event carrying that error code
- **AND** SHALL terminate the subagent's child session

#### Scenario: Content or a tool call resets the empty streak
- **WHEN** a subagent returns an empty response followed by a response with content or tool calls
- **THEN** the empty streak SHALL be reset
- **AND** the run SHALL continue or complete on the non-empty response

### Requirement: The child monitor reports a failsafe failure's reason
When a subagent job fails with a failsafe error code (`subagent_timeout`, `subagent_error_loop`, `subagent_no_progress`), the `subagent_failed` event the child monitor appends to the parent job SHALL carry the failsafe's own reason (`timeout`, `error_loop`, `no_progress`) together with the error code and message, so the parent's timeline names what actually happened. Every other child outcome SHALL keep its existing reason. `wait_for_subagent` SHALL return a failsafe failure to the parent as an error naming the child and the error code.

#### Scenario: A timed-out child is reported with its failsafe reason
- **WHEN** a subagent job fails with error code `subagent_timeout`
- **THEN** the monitor SHALL append a `subagent_failed` event to the parent job with `reason: "timeout"` and the `subagent_timeout` error code
- **AND** `wait_for_subagent` SHALL return an error naming the child and the error code

#### Scenario: A non-failsafe failure keeps its existing reason
- **WHEN** a subagent job fails with any other error code
- **THEN** the monitor SHALL append a `subagent_failed` event whose `reason` is the terminal status the child reached, as before
