## ADDED Requirements

### Requirement: Subagent waits are authorized to the current parent and session

`wait_for_subagent` SHALL authorize the requested child job against the current parent job identity and verify that the current parent job belongs to the current orchestrator session before it subscribes to child events, polls child state, or returns an outcome. A missing job, a job whose persisted parent is different, or a current parent whose persisted session does not match the bound session SHALL produce an error result that does not disclose the requested job's result text, status, failure details, or cancellation reason. This authorization boundary SHALL use the existing persisted job relationships and SHALL NOT alter the behavior of an authorized wait.

#### Scenario: An owned child result remains awaitable

- **WHEN** a parent job waits for a child job whose persisted parent job is the current parent and whose current parent belongs to the current orchestrator session
- **THEN** `wait_for_subagent` SHALL return the child's existing terminal outcome, including result text for a successful child

#### Scenario: A foreign parent job is rejected before polling

- **WHEN** a parent job requests a child job in the current orchestrator session whose persisted parent job is different
- **THEN** `wait_for_subagent` SHALL return an error without subscribing to or polling the requested child
- **AND** the response SHALL NOT contain the foreign child's result text, status, or failure details

#### Scenario: A foreign session job is rejected before polling

- **WHEN** a parent job requests a child job whose persisted parent job belongs to a different session from the current orchestrator session
- **THEN** `wait_for_subagent` SHALL return an error without subscribing to or polling the requested child
- **AND** the response SHALL NOT contain the foreign child's result text, status, or failure details

#### Scenario: Authorized timeout and cancellation behavior is unchanged

- **WHEN** an authorized child remains active until the wait budget expires or the current parent job requests cancellation
- **THEN** `wait_for_subagent` SHALL return the existing timeout or parent-cancellation error outcome
- **AND** a timeout SHALL retain its existing parent `subagent_failed` event recording without cancelling the child
